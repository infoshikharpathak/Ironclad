"""Policy retrieval eval: does /policies/search find the right section?

    python -m evals.policies.run [--max-tokens 400 120 60] [--min-scores 0.3 0.35 0.4 0.45 0.5]

For each chunk size, indexes the policies into a throwaway schema (needs
DATABASE_URL and OPENAI_API_KEY), embeds the questions once, and scores
every minimum-score threshold from the same rankings. Reports, on the 20
answerable questions: recall@1, recall@3, MRR@3, and how often an answerable
question came back empty; on the 5 unanswerable ones: how often they came
back empty (correct). Writes results/grid.json and results/summary.md.

Hit rules: a question with match "any" is a hit if any listed section is in
the top k; "all" (questions spanning two documents) needs every listed
section in the top 3 for recall@3, and counts a hit at 1 if the first result
is one of them. MRR uses the rank of the first listed section.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

import asyncpg

from app import config
from app.policies import chunking, embeddings, store

HERE = Path(__file__).resolve().parent
DB_DIR = Path(__file__).resolve().parents[3] / "db"


def load_questions() -> list[dict]:
    return [json.loads(l) for l in (HERE / "questions.jsonl").read_text().splitlines() if l.strip()]


def score(questions: list[dict], ranked: dict[str, list[dict]], threshold: float, k: int = 3) -> dict:
    ans = [q for q in questions if q["match"] != "none"]
    una = [q for q in questions if q["match"] == "none"]
    r1 = r3 = rr = empty_ans = 0.0
    misses = []
    for q in ans:
        top = [(r["doc_slug"], r["section"]) for r in ranked[q["id"]] if r["score"] >= threshold][:k]
        want = [(e["doc_slug"], e["section"]) for e in q["expected"]]
        if not top:
            empty_ans += 1
        hit1 = bool(top) and top[0] in want
        hit3 = all(w in top for w in want) if q["match"] == "all" else any(w in top for w in want)
        rank = next((i + 1 for i, t in enumerate(top) if t in want), None)
        r1 += hit1
        r3 += hit3
        rr += 1 / rank if rank else 0
        if not hit3:
            misses.append(q["id"])
    empty_una = sum(1 for q in una if not [r for r in ranked[q["id"]] if r["score"] >= threshold])
    return {"threshold": threshold, "recall_at_1": round(r1 / len(ans), 3), "recall_at_3": round(r3 / len(ans), 3),
            "mrr_at_3": round(rr / len(ans), 3), "answerable_empty": round(empty_ans / len(ans), 3),
            "unanswerable_empty": round(empty_una / len(una), 3), "misses_at_3": misses}


async def rankings(max_tokens: int, embedder, questions: list[dict], qvecs: list[list[float]]) -> tuple[dict, int, int]:
    schema = "eval_" + uuid.uuid4().hex[:8]
    admin = await asyncpg.connect(config.DATABASE_URL)
    await admin.execute(f"CREATE SCHEMA {schema}")
    try:
        conn = await asyncpg.connect(config.DATABASE_URL, server_settings={"search_path": f"{schema},public"})
        await conn.execute((DB_DIR / "003_policies.sql").read_text())
        chunks = chunking.load_policies(max_tokens=max_tokens, overlap_tokens=max(10, max_tokens // 10))
        report = await store.index_chunks(conn, chunks, embedder)
        ranked = {}
        for q, vec in zip(questions, qvecs):
            rows = await conn.fetch(
                "SELECT doc_slug, section, 1 - (embedding <=> $1::vector) AS score FROM policy_chunks "
                "ORDER BY embedding <=> $1::vector LIMIT 5", store.to_pgvector(vec))
            seen, out = set(), []
            for r in rows:  # a split section can appear twice; keep its best chunk
                key = (r["doc_slug"], r["section"])
                if key not in seen:
                    seen.add(key)
                    out.append({"doc_slug": r["doc_slug"], "section": r["section"], "score": round(float(r["score"]), 4)})
            ranked[q["id"]] = out
        await conn.close()
        return ranked, report.tokens, len(chunks)
    finally:
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


async def main_async(args) -> None:
    embedder = embeddings.default_embedder()
    if embedder is None:
        raise SystemExit("OPENAI_API_KEY is not set")
    questions = load_questions()
    qvecs, q_tokens = await embedder.embed([q["question"] for q in questions])
    tokens = q_tokens
    grid = []
    for max_tokens in args.max_tokens:
        ranked, idx_tokens, n_chunks = await rankings(max_tokens, embedder, questions, qvecs)
        tokens += idx_tokens
        for t in args.min_scores:
            grid.append({"max_tokens": max_tokens, "chunks": n_chunks, **score(questions, ranked, t)})
        (HERE / "results" / f"rankings-{max_tokens}.json").write_text(json.dumps(ranked, indent=2) + "\n")
    cost = embeddings.cost_usd(embedder.model, tokens)
    result = {"model": embedder.model, "questions": len(questions), "grid": grid, "tokens": tokens, "cost_usd": cost,
              "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (HERE / "results" / "grid.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [f"# Policy retrieval eval", "",
             f"{embedder.model}, {len(questions)} questions (20 answerable, 5 not), top 3. "
             f"{tokens} embedding tokens, ${cost}. {result['finished_at']}.", "",
             "| Chunk max tokens | Chunks | Min score | Recall@1 | Recall@3 | MRR@3 | Answerable came back empty | Unanswerable came back empty | Misses @3 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for g in grid:
        lines.append(f"| {g['max_tokens']} | {g['chunks']} | {g['threshold']:.2f} | {g['recall_at_1']:.2f} | {g['recall_at_3']:.2f} | "
                     f"{g['mrr_at_3']:.2f} | {g['answerable_empty']:.2f} | {g['unanswerable_empty']:.2f} | "
                     f"{', '.join(g['misses_at_3']) or '—'} |")
    (HERE / "results" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m evals.policies.run")
    p.add_argument("--max-tokens", type=int, nargs="+", default=[400, 120, 60])
    p.add_argument("--min-scores", type=float, nargs="+", default=[0.30, 0.35, 0.40, 0.45, 0.50])
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
