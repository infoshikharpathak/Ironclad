"""Run the real banking agent (gpt-4o-mini, Ironclad's instructions, real
Anvil) on each scenario and save the replies it actually wrote.

The bank is a scenario-specific stub (scenarios.jsonl): same response shapes
as bank-service, with refusals and planted injections made reproducible. For
attack scenarios, tool_response scanning is turned off, so the reply is what
a hijacked agent writes; the output scan is what's being measured.

    cd agent-service && python -m evals.replies.run --runs 2 --out ../../anvil/evals/replies/replies-ironclad.jsonl

Needs OPENAI_API_KEY. With POLICY_SEARCH_URL (a running bank-service),
search_policies goes to the bank's real search with the agent's own key;
without it, a keyword stand-in over the public sections. Each reply is saved with its trace ID and the model's
raw text (before any output check).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import sys
import uuid
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # the Ironclad repo
sys.path.insert(0, str(HERE.parents[1]))  # agent-service

ACCOUNTS = [
    {"id": "acc_demo_user_checking", "name": "Checking", "account_type": "checking", "balance": 10000.0,
     "currency": "USD"},
    {"id": "acc_demo_user_savings", "name": "Savings", "account_type": "savings", "balance": 5000.0,
     "currency": "USD"},
]
DIRECTORY = [
    {"account_number": "ACC-10042-CHK", "owner_name": "Alice Johnson", "account_type": "checking", "currency": "USD"},
    {"account_number": "ACC-10043-CHK", "owner_name": "Bob Smith", "account_type": "checking", "currency": "USD"},
    {"account_number": "ACC-10044-SAV", "owner_name": "Carol Davis", "account_type": "savings", "currency": "USD"},
]
NAMES = {d["account_number"]: d["owner_name"] for d in DIRECTORY}
NAMES.update({a["id"]: a["name"] for a in ACCOUNTS})


def load_sections() -> list[dict]:
    """Public policy sections, like the bank's parent sections."""
    out = []
    for path in sorted((ROOT / "bank-service" / "policies").glob("*.md")):
        text = path.read_text()
        if "level: public" not in text:
            continue
        title = re.search(r"^# (.+)$", text, re.M).group(1)
        for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
            out.append({"doc_slug": path.stem, "doc_title": title, "section": m.group(1).strip(),
                        "effective_date": "2026-10-01", "content": " ".join(m.group(2).split())})
    return out


SECTIONS = load_sections()
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an the to of for and or is are be i my me you your can do does how what when if in on it with".split())


def _stems(text: str) -> set[str]:
    return {w[:-1] if w.endswith("s") and len(w) > 3 else w for w in _WORD.findall(text.lower()) if w not in _STOP}


def search(q: str, top_k: int) -> list[dict]:
    """Keyword overlap over public sections: a stand-in for the bank's
    hybrid search, good enough to give the agent realistic results."""
    words = _stems(q)
    scored = []
    for s in SECTIONS:
        text = _stems(s["doc_title"] + " " + s["section"] + " " + s["content"])
        hits = len(words & text)
        if hits:
            scored.append((hits / max(len(words), 1), s))
    scored.sort(key=lambda x: -x[0])
    return [dict(s, score=round(0.4 + 0.5 * sc, 3)) for sc, s in scored[:top_k] if sc >= 0.34]


class ScenarioBank:
    def __init__(self, sc: dict):
        self.sc = sc
        self.accounts = copy.deepcopy(ACCOUNTS)
        for a in self.accounts:
            if a["account_type"] in (sc.get("balances") or {}):
                a["balance"] = sc["balances"][a["account_type"]]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        sc, path = self.sc, request.url.path
        if path == "/accounts":
            return httpx.Response(200, json={"accounts": self.accounts})
        if path.startswith("/accounts/") and path.endswith("/transactions"):
            extra = {"notice": sc["transactions_notice"]} if sc.get("transactions_notice") else {}
            return httpx.Response(200, json={**extra, "limit": 20, "offset": 0, "transactions": [
                {"id": "txn_4f1a9c2e7b10", "from_account": "ACC-10043-CHK", "to_account": "acc_demo_user_checking",
                 "amount": 1.0 if sc.get("memo") else 42.5, "status": "confirmed", "initiated_by": "user",
                 "description": sc.get("memo") or "Dinner split", "created_at": "2026-11-21T19:02:11+00:00"},
                {"id": "txn_88c3d0a91f2e", "from_account": "acc_demo_user_checking", "to_account": "ACC-10042-CHK",
                 "amount": 60.0, "status": "confirmed", "initiated_by": "user", "description": "Groceries",
                 "created_at": "2026-11-20T12:40:00+00:00"},
            ]})
        if path.startswith("/accounts/"):
            acc = next((a for a in self.accounts if a["id"] == path.rsplit("/", 1)[1]), None)
            return httpx.Response(200, json=acc) if acc else httpx.Response(404, json={"error": "ACCOUNT_NOT_FOUND"})
        if path == "/directory":
            entries = copy.deepcopy(DIRECTORY)
            if sc.get("directory_note"):
                entries[0]["owner_name"] = sc["directory_note"]
            return httpx.Response(200, json={"accounts": entries})
        if path.startswith("/directory/lookup/"):
            number = path.rsplit("/", 1)[1]
            own = next((a for a in self.accounts if a["id"] == number), None)
            if own:  # like the bank: the user's own account IDs resolve too
                return httpx.Response(200, json={"account_number": number, "owner_name": own["name"],
                                                 "account_type": own["account_type"], "currency": "USD"})
            if number not in NAMES:
                return httpx.Response(404, json={"error": "ACCOUNT_NOT_FOUND", "message": f"No account {number}"})
            owner = sc.get("lookup_owner") if number == "ACC-10043-CHK" and sc.get("lookup_owner") else NAMES[number]
            return httpx.Response(200, json={"account_number": number, "owner_name": owner,
                                             "account_type": "checking", "currency": "USD"})
        if path == "/policies/search":
            real = os.getenv("POLICY_SEARCH_URL")  # e.g. http://localhost:8001: the bank's real search
            if real:
                resp = httpx.get(f"{real.rstrip('/')}/policies/search", params=dict(request.url.params),
                                 headers={"Authorization": request.headers.get("authorization", "")}, timeout=30)
                results = resp.json().get("results", [])
            else:
                results = search(request.url.params["q"], int(request.url.params.get("top_k", 3)))
            if sc.get("policy_inject") and results:
                results[0]["content"] += " " + sc["policy_inject"]
            return httpx.Response(200, json={"query": request.url.params["q"], "min_score": 0.43, "results": results})
        if path == "/transfers/initiate":
            body = json.loads(request.content)
            if sc.get("initiate_error"):
                return httpx.Response(sc["initiate_error"][0], json=sc["initiate_error"][1])
            to = body["to_account"]
            return httpx.Response(200, json={
                "transfer_id": "txn_" + uuid.uuid4().hex[:12], "status": "pending_otp",
                "message": "OTP sent to your bank dashboard. Please confirm.", "amount": body["amount"],
                "from_account": body["from_account"], "to_account": to,
                "to_name": sc.get("lookup_owner") if to == "ACC-10043-CHK" and sc.get("lookup_owner") else NAMES.get(to),
                "expires_at": "2026-11-22T18:05:00+00:00", "idempotent_replay": False})
        if path.startswith("/transfers/") and path.endswith("/status"):
            return httpx.Response(200, json={"transfer_id": path.split("/")[2], "status": "pending_otp"})
        if path.startswith("/transfers/") and path.endswith(("/flag", "/flag-recent")):
            return httpx.Response(200, json={"flagged": True})
        return httpx.Response(404, json={"error": "NOT_FOUND", "message": f"scenario bank has no {path}"})


async def run_one(sc: dict, run: int, model: str) -> dict:
    import app.main as main
    from garrison import Platform, load_config

    raw = yaml.safe_load(open(main.CONFIG_PATH))
    raw["agents"][main.AGENT_ID]["model"] = model
    if sc.get("attack"):  # the output scan sees what a hijacked agent writes
        for tool in raw["apps"]["ironclad"]["tools"].values():
            tool["injection_scanning"] = False
    bank = ScenarioBank(sc)
    platform = Platform(load_config(raw), app=main.APP, prepare_tool_call=main.prepare_tool_call,
                        http_transport=httpx.MockTransport(bank), sinks=[])
    await platform.start()
    try:
        sid = f"replies-{sc['id']}-{run}-{uuid.uuid4().hex[:4]}"
        reply = await platform.run_agent(main.AGENT, sc["message"], session_id=sid)
    finally:
        await platform.close()
    trace = reply.trace
    agent = next((a for a in trace.get("agents", []) if a.get("raw_output")), {})
    calls = [{"tool": c["tool"], "params": {k: v for k, v in (c.get("params") or {}).items()
                                            if k not in ("user_id", "idempotency_key", "initiated_by")},
              "status": c.get("status"), "violation": c.get("violation")} for c in trace.get("tool_calls", [])]
    return {"scenario": sc["id"], "category": sc["category"], "run": run, "trace_id": reply.trace_id,
            "agent": main.AGENT_ID, "user_request": sc["message"], "attack": bool(sc.get("attack")),
            "tool_calls": calls, "text": agent.get("raw_output") or reply.content}


async def main_async(args) -> None:
    from agent_forge import db  # noqa: F401  (Agent Forge's run store)

    scenarios = [json.loads(line) for line in (HERE / "scenarios.jsonl").read_text().splitlines() if line.strip()]
    if args.only:
        scenarios = [s for s in scenarios if s["id"] in args.only]
    out = []
    for sc in scenarios:
        for run in range(1, args.runs + 1):
            row = await run_one(sc, run, args.model)
            out.append(row)
            print(f"{row['scenario']} #{run} {row['trace_id']}: {row['text'][:110]!r}", flush=True)
    Path(args.out).write_text("".join(json.dumps(r) + "\n" for r in out))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--out", required=True)
    p.add_argument("--only", nargs="*")
    args = p.parse_args()
    os.environ.setdefault("AGENT_FORGE_DB_PATH", str(Path(args.out).with_suffix(".forge.db")))
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
