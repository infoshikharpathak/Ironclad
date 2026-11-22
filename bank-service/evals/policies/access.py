"""Access eval: internal-only questions, asked with a public-only key and
with an internal key, through the real endpoint.

    POLICY_PARTNER_KEY=pk_... POLICY_INTERNAL_KEY=pk_... \\
        python -m evals.policies.access [--base-url http://localhost:8001]

Expected: with the partner (public-only) key, no question returns any
section of an internal document (adversarial wording included). With the
internal key, each question returns its internal document in the top 3.
Writes results/access.json and results/access.md.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx

from app.policies import chunking

HERE = Path(__file__).resolve().parent


def internal_slugs() -> set[str]:
    return {c.doc_slug for c in chunking.load_policies() if c.level == "internal"}


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m evals.policies.access")
    p.add_argument("--base-url", default="http://localhost:8001")
    args = p.parse_args()
    keys = {"partner": os.environ["POLICY_PARTNER_KEY"], "internal": os.environ["POLICY_INTERNAL_KEY"]}
    internal = internal_slugs()
    questions = [json.loads(l) for l in (HERE / "access.jsonl").read_text().splitlines() if l.strip()]
    rows = []
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        for q in questions:
            row = {"id": q["id"], "kind": q["kind"], "question": q["question"], "expected_doc": q["internal_doc"]}
            for who, key in keys.items():
                r = client.get("/policies/search", params={"q": q["question"], "top_k": 3},
                               headers={"Authorization": f"Bearer {key}"})
                r.raise_for_status()
                results = r.json()["results"]
                row[who] = {"docs": [x["doc_slug"] for x in results],
                            "internal_returned": sum(x["doc_slug"] in internal for x in results)}
            row["partner_ok"] = row["partner"]["internal_returned"] == 0
            row["internal_ok"] = q["internal_doc"] in row["internal"]["docs"]
            rows.append(row)
    summary = {
        "questions": len(rows),
        "partner_internal_chunks_returned": sum(r["partner"]["internal_returned"] for r in rows),
        "partner_questions_with_any_result": sum(bool(r["partner"]["docs"]) for r in rows),
        "internal_answered": sum(r["internal_ok"] for r in rows),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (HERE / "results" / "access.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n")
    lines = ["# Policy access eval", "",
             f"{summary['questions']} questions answered only by internal documents. "
             f"Partner (public-only) key: {summary['partner_internal_chunks_returned']} internal sections returned "
             f"({summary['partner_questions_with_any_result']} questions got some public result). "
             f"Internal key: {summary['internal_answered']}/{summary['questions']} returned the right internal document "
             f"in the top 3. {summary['finished_at']}.", "",
             "| Id | Kind | Question | Partner key: docs returned | Internal key: docs returned | Expected |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['kind']} | {r['question']} | {', '.join(r['partner']['docs']) or '(empty)'} | "
                     f"{', '.join(r['internal']['docs']) or '(empty)'} | {r['expected_doc']} |")
    (HERE / "results" / "access.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))


if __name__ == "__main__":
    main()
