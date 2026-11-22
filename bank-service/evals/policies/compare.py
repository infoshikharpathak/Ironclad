"""Compare retrieval setups on the dev and held-out questions.

    python -m evals.policies.compare

Setups (all over the same ~60-token child chunks):
  vector          cosine similarity, minimum 0.43 (tuned earlier on dev)
  keyword         Postgres full-text search (ts_rank_cd), minimum rank tuned on dev
  hybrid          vector + keyword, reciprocal rank fusion, "not covered" gate tuned on dev
  hybrid_parent   hybrid, then grouped by parent section (each section once), gate tuned on dev

Settings are chosen on questions.jsonl (dev) only, by the share of all dev
questions handled correctly (an answerable one with a right section in the
top 3, an unanswerable one empty; ties: recall@1, then MRR), then applied
unchanged to heldout.jsonl. For the hybrid setups that includes the fusion
knobs (RRF k, keyword weight, minimum full-text rank to enter the fusion)
and the "not covered" gate. Needs DATABASE_URL and OPENAI_API_KEY. Writes
results/compare.json and results/compare.md.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time
import uuid
from pathlib import Path

import asyncpg

from app import config
from app.policies import chunking, embeddings, store

HERE = Path(__file__).resolve().parent
DB_DIR = Path(__file__).resolve().parents[3] / "db"
VECTOR_MIN = 0.43
KEYWORD_MINS = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7]
VECTOR_GATES = [0.35, 0.38, 0.40, 0.42, 0.43, 0.45]
KEYWORD_GATES = [0.3, 0.5, 0.7, 1.0, 1.5, float("inf")]
RRF_KS = [60, 20, 5]
KEYWORD_WEIGHTS = [1.0, 0.5, 0.25]
KEYWORD_FUSE_MINS = [0.0, 0.1, 0.2, 0.4]


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in (HERE / name).read_text().splitlines() if l.strip()]


def score(questions: list[dict], results: dict[str, list[tuple[str, str]]]) -> dict:
    ans = [q for q in questions if q["match"] != "none"]
    una = [q for q in questions if q["match"] == "none"]
    r1 = r3 = rr = empty = 0.0
    misses = []
    for q in ans:
        top = results[q["id"]][:3]
        want = [(e["doc_slug"], e["section"]) for e in q["expected"]]
        empty += not top
        hit1 = bool(top) and top[0] in want
        hit3 = all(w in top for w in want) if q["match"] == "all" else any(w in top for w in want)
        rank = next((i + 1 for i, t in enumerate(top) if t in want), None)
        r1 += hit1
        r3 += hit3
        rr += 1 / rank if rank else 0
        if not hit3:
            misses.append(q["id"])
    una_empty = sum(1 for q in una if not results[q["id"]])
    return {"recall_at_1": round(r1 / len(ans), 3), "recall_at_3": round(r3 / len(ans), 3),
            "mrr_at_3": round(rr / len(ans), 3), "answerable_empty": round(empty / len(ans), 3),
            "unanswerable_empty": round(una_empty / len(una), 3), "misses_at_3": misses}


def run_setup(mode: str, gate: store.Gate, questions: list[dict], cands: dict) -> dict:
    results = {}
    for q in questions:
        vec_rows, kw_rows = cands[q["id"]]
        picked = store.select(vec_rows, kw_rows, mode, 3, gate, VECTOR_MIN if mode == "vector" else None)
        results[q["id"]] = [(r["doc_slug"], r["section"]) for r, _ in picked]
    return score(questions, results)


def objective(m: dict, n_ans: int = 20, n_una: int = 5) -> tuple:
    correct = m["recall_at_3"] * n_ans + m["unanswerable_empty"] * n_una
    return (round(correct, 6), m["recall_at_1"], m["mrr_at_3"])


async def main_async() -> None:
    embedder = embeddings.default_embedder()
    if embedder is None:
        raise SystemExit("OPENAI_API_KEY is not set")
    dev, held = load("questions.jsonl"), load("heldout.jsonl")
    schema = "cmp_" + uuid.uuid4().hex[:8]
    admin = await asyncpg.connect(config.DATABASE_URL)
    await admin.execute(f"CREATE SCHEMA {schema}")
    try:
        pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=4,
                                         server_settings={"search_path": f"{schema},public"})
        async with pool.acquire() as conn:
            for name in ("003_policies.sql", "004_policy_hybrid.sql"):
                await conn.execute((DB_DIR / name).read_text())
            report = await store.index_chunks(conn, chunking.load_policies(), embedder)
        qvecs, q_tokens = await embedder.embed([q["question"] for q in dev + held])
        cands = {}
        for q, vec in zip(dev + held, qvecs):
            cands[q["id"]] = (await store.vector_children(pool, vec, embedder.model),
                              await store.keyword_children(pool, q["question"]))
        await pool.close()
    finally:
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()

    setups = {}
    setups["vector"] = {"params": {"min_score": VECTOR_MIN}, "gate": store.Gate(vector_min=VECTOR_MIN)}
    best = max(KEYWORD_MINS, key=lambda k: objective(run_setup("keyword", store.Gate(keyword_min=k), dev, cands)))
    setups["keyword"] = {"params": {"min_rank": best}, "gate": store.Gate(keyword_min=best)}
    grid_log = {}
    for mode in ("hybrid", "hybrid_parent"):
        tried = []
        for vg, kg, rk, kw, km in itertools.product(VECTOR_GATES, KEYWORD_GATES, RRF_KS, KEYWORD_WEIGHTS,
                                                    KEYWORD_FUSE_MINS):
            gate = store.Gate(vector=vg, keyword=kg, rrf_k=rk, keyword_weight=kw, keyword_fuse_min=km)
            tried.append(((vg, kg, rk, kw, km), run_setup(mode, gate, dev, cands)))
        (vg, kg, rk, kw, km), _ = max(tried, key=lambda t: objective(t[1]))
        grid_log[mode] = [{"vector_gate": v, "keyword_gate": (None if k == float("inf") else k), "rrf_k": r,
                           "keyword_weight": w, "keyword_fuse_min": f, **m} for (v, k, r, w, f), m in tried]
        setups[mode] = {"params": {"vector_gate": vg, "keyword_gate": None if kg == float("inf") else kg,
                                   "rrf_k": rk, "keyword_weight": kw, "keyword_fuse_min": km},
                        "gate": store.Gate(vector=vg, keyword=kg, rrf_k=rk, keyword_weight=kw, keyword_fuse_min=km)}

    out = {"model": embedder.model, "chunks": report.total, "sections": report.sections,
           "tokens": report.tokens + q_tokens, "cost_usd": embeddings.cost_usd(embedder.model, report.tokens + q_tokens),
           "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "setups": {}, "grid": grid_log}
    for name, s in setups.items():
        out["setups"][name] = {"params": s["params"], "dev": run_setup(name, s["gate"], dev, cands),
                               "heldout": run_setup(name, s["gate"], held, cands)}
    (HERE / "results" / "compare.json").write_text(json.dumps(out, indent=2) + "\n")
    lines = ["# Policy retrieval: four setups", "",
             f"{embedder.model}; {report.total} child chunks, {report.sections} parent sections; top 3. "
             f"Thresholds tuned on dev ({len(dev)} questions) only, then applied to held-out ({len(held)}). "
             f"{out['tokens']} embedding tokens, ${out['cost_usd']}. {out['finished_at']}.", "",
             "| Setup | Params | Set | Recall@1 | Recall@3 | MRR@3 | Answerable empty | Unanswerable empty | Misses @3 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, s in out["setups"].items():
        params = ", ".join(f"{k} {v}" for k, v in s["params"].items())
        for split in ("dev", "heldout"):
            m = s[split]
            lines.append(f"| {name} | {params} | {split} | {m['recall_at_1']:.2f} | {m['recall_at_3']:.2f} | "
                         f"{m['mrr_at_3']:.2f} | {m['answerable_empty']:.2f} | {m['unanswerable_empty']:.2f} | "
                         f"{', '.join(m['misses_at_3']) or '—'} |")
    (HERE / "results" / "compare.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main_async())
