"""Ironclad Agent Service: the banking assistant, on the bastion SDK.

bastion runs the agent (Agent Forge) under Anvil governance: the
agent, its tools and its policy all come from anvil-ironclad.yaml. This
service only adds what is Ironclad-specific: the signed-in user's ID on
every tool call, and the HTTP shapes the web UI expects.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()
# Local dev fallback: load .env from a sibling agent-forge checkout if present.
_forge_env = os.path.join(os.path.dirname(__file__), "../../../agent-forge/.env")
if os.path.exists(_forge_env):
    load_dotenv(_forge_env)

from bastion import Platform, load_config  # noqa: E402

from . import approval  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("ironclad-agent")

# docker-compose sets ANVIL_CONFIG_PATH (the yaml is mounted at /app/anvil-ironclad.yaml).
# Local dev falls back to the repo-root file next to agent-service/.
CONFIG_PATH = os.environ.get("ANVIL_CONFIG_PATH") or os.path.join(
    os.path.dirname(__file__), "../../anvil-ironclad.yaml"
)
APP = "ironclad"
AGENT = "banking_agent"
AGENT_ID = f"{APP}.{AGENT}"
POLICY_LABEL = "ironclad-banking"
BANK_USER_ID = "demo_user"
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]


def prepare_tool_call(ctx: Any, tool: str, params: dict[str, Any]) -> dict[str, Any]:
    """Values the model must not choose, filled in before Anvil sees the call."""
    if tool in ("get_accounts", "get_account", "get_transactions", "get_transfer_status", "initiate_transfer"):
        params["user_id"] = BANK_USER_ID
    if tool == "initiate_transfer":
        params["initiated_by"] = "agent"
        # Always the service's, one per transfer: the tool's schema doesn't
        # declare idempotency_key, so Anvil blocks a model that sends one (a
        # reused key would replay an earlier transfer instead of starting one).
        params["idempotency_key"] = f"agent_{uuid.uuid4().hex}"
    return params


def make_flagger(bank_url, transport: Any = None):
    """on_output_blocked hook: when Anvil blocks the agent's reply, flag the
    pending transfers that turn started. They stay pending (the block may be
    a false positive); the OTP modal warns the user before they approve.
    *bank_url* is a callable (the base URL can change with a remote bundle)."""

    async def flag(agent_id: str, tool_calls: list[dict[str, Any]], reason: str) -> list[dict[str, Any]]:
        out = []
        for call in tool_calls:
            data = call.get("response") if isinstance(call.get("response"), dict) else {}
            if call.get("tool") != "initiate_transfer" or not call.get("success") or data.get("status") != "pending_otp":
                continue
            transfer_id = data["transfer_id"]
            try:
                async with httpx.AsyncClient(timeout=10, transport=transport) as client:
                    resp = await client.post(f"{bank_url()}/transfers/{transfer_id}/flag",
                                             json={"user_id": BANK_USER_ID, "reason": reason[:500]})
                ok = resp.status_code < 400
            except httpx.HTTPError:
                ok = False
            (logger.warning if ok else logger.error)(
                "Blocked reply: %s pending transfer %s", "flagged" if ok else "could not flag", transfer_id)
            out.append({"tool": "initiate_transfer", "id": transfer_id, "what": "a pending transfer",
                        "where": "Ironclad", "flagged": ok})
        return out

    return flag


def build_platform(**platform_kwargs: Any) -> Platform:
    """The agent's platform, from the bastion control plane or the local YAML.

    Remote mode, when BASTION_URL and BASTION_KEY are both set: the
    bundle (tools, agent, prompt version, policy) comes from the service and
    is re-checked every BASTION_REFRESH_SECONDS (default 30), so prompt
    edits and rollbacks there apply without a restart. Otherwise the local
    anvil-ironclad.yaml is used, as before, with the bank at
    IRONCLAD_BASE_URL if that's set (containers can't reach localhost:8001).

    *platform_kwargs* go to Platform (tests pass stub LLM clients, an HTTP
    transport for the bank, and in remote mode a service transport).
    """
    url, key = os.getenv("BASTION_URL"), os.getenv("BASTION_KEY")
    bank_url = os.getenv("IRONCLAD_BASE_URL")
    holder: dict[str, Platform] = {}
    platform_kwargs.setdefault("on_output_blocked", make_flagger(
        lambda: holder["platform"].config.platform.apps[APP]["base_url"].rstrip("/"),
        platform_kwargs.get("http_transport"),
    ))
    if url and key:
        if bank_url:
            logger.warning("IRONCLAD_BASE_URL is ignored in remote mode: set the ironclad app's "
                           "base_url on the bastion service instead.")
        platform = Platform.from_service(
            url, key, prepare_tool_call=prepare_tool_call,
            refresh_interval=float(os.getenv("BASTION_REFRESH_SECONDS", "30")),
            **platform_kwargs,
        )
        if platform.app != APP:
            raise RuntimeError(f"BASTION_KEY belongs to app {platform.app!r}, not {APP!r}.")
        logger.info("bastion remote mode: %s, revision %s", url, platform.bundle_revision)
        holder["platform"] = platform
        platform.bank_transport = platform_kwargs.get("http_transport")  # for the approval-line flags
        return platform
    raw = yaml.safe_load(open(CONFIG_PATH))
    if bank_url:  # e.g. http://bank-service:8001 in docker-compose; the YAML says localhost
        raw["apps"][APP]["base_url"] = bank_url.rstrip("/")
    if os.getenv("OPENAI_MODEL"):  # local mode only; in remote mode the service decides the model
        raw["agents"][AGENT_ID]["model"] = os.environ["OPENAI_MODEL"]
    platform = Platform(load_config(raw), app=APP, prepare_tool_call=prepare_tool_call, **platform_kwargs)
    holder["platform"] = platform
    platform.bank_transport = platform_kwargs.get("http_transport")  # for the approval-line flags
    return platform


@asynccontextmanager
async def lifespan(app: FastAPI):
    platform = build_platform()
    await platform.start()
    app.state.platform = platform
    logger.info("Ironclad Agent Service ready (agents=%s)", [a["name"] for a in platform.list_agents()])
    yield
    await platform.close()


app = FastAPI(title="Ironclad Agent Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _platform() -> Platform:
    return app.state.platform


class ChatRequest(BaseModel):
    message: str
    session_id: str
    """One per browser tab. Turns in a session share the agent's memory and
    Anvil's sequence state (look-ups in one message satisfy a transfer in the next)."""


class ResetRequest(BaseModel):
    session_id: str


class ToolCallInfo(BaseModel):
    tool: str
    input: dict[str, Any]
    result: dict[str, Any]
    blocked: bool = False


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallInfo] = []


def _tool_call_info(call: dict[str, Any]) -> ToolCallInfo:
    if call["success"]:
        data = call["response"]
        result = data if isinstance(data, dict) else {"data": data}
    else:
        message = call["correction"] or "Tool call blocked by governance."
        result = {"error": message, "blocked": True}
    return ToolCallInfo(tool=call["tool"], input=call["params"], result=result, blocked=not call["success"])


@app.get("/health")
def health():
    return {"status": "ok", "anvil_session": None}


@app.post("/agent/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    started = datetime.now(timezone.utc)
    try:
        reply = await _platform().run_agent(AGENT, req.message, session_id=req.session_id)
    except Exception as exc:
        logger.exception("Agent error")
        return ChatResponse(reply=f"I encountered an error: {exc}", tool_calls=[])
    calls = reply.trace.get("tool_calls", [])
    # The approval line is the system's, added after the output scan and
    # after any fallback reply (see app/approval.py).
    lines, to_flag, flag_recent = approval.plan(calls)
    if to_flag or flag_recent:
        await _flag_withheld(to_flag, started if flag_recent else None)
    return ChatResponse(reply=approval.append(reply.content, lines),
                        tool_calls=[_tool_call_info(c) for c in calls])


async def _flag_withheld(transfer_ids: list[str], since: datetime | None) -> None:
    """Flag transfers whose initiate response Anvil withheld. With *since*,
    the host couldn't read which one it was: flag every pending agent
    transfer this user has had since the turn started."""
    platform = _platform()
    base = platform.config.platform.apps[APP]["base_url"].rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10, transport=getattr(platform, "bank_transport", None)) as client:
            for tid in transfer_ids:
                await client.post(f"{base}/transfers/{tid}/flag",
                                  json={"user_id": BANK_USER_ID, "reason": approval.WITHHELD_REASON})
            if since is not None:
                await client.post(f"{base}/transfers/flag-recent", json={
                    "user_id": BANK_USER_ID, "since": since.isoformat(), "reason": approval.WITHHELD_REASON})
    except httpx.HTTPError:
        logger.exception("Could not flag withheld transfers %s", transfer_ids)


@app.post("/agent/reset")
async def reset_agent(req: ResetRequest):
    await _platform().end_session(req.session_id)
    return {"status": "ok", "message": "Conversation and Anvil session reset."}


# ── Trace API ────────────────────────────────────────────────────────────────

def _tool_records(session_id: str) -> list[dict[str, Any]]:
    """The agent's tool-call records in this session (agent checks excluded)."""
    return [
        r for r in _platform().session_records(session_id)
        if r["kind"] == "tool" and r["agent"] == AGENT_ID
    ]


def _short(name: str) -> str:
    return name.split(".", 1)[1] if "." in name else name


_BLOCKED_RESULTS = ("blocked", "response_withheld")


@app.get("/traces")
def get_traces(session_id: str = Query(..., description="The browser tab's agent session")):
    """Return the agent's tool-call trace events for a session."""
    traces = []
    for i, c in enumerate(_tool_records(session_id)):
        result = c["result"]
        traces.append({
            "id": f"trace_{i:03d}",
            "timestamp": c["timestamp"],
            "agent_id": _short(c["agent"]),
            "tool": _short(c["tool"]),
            "parameters": c["params"],
            # A withheld response ran at the bank, but the agent never saw it
            # (e.g. an injection in a memo): for the user that's a block.
            "decision": "blocked" if result in _BLOCKED_RESULTS else "allowed",
            "result": result,
            "reason": c["correction_message"] or ("Allowed by policy" if result == "success" else "Response withheld"),
            "violation": c["violation"],
            "policy_rule": _violation_to_rule(c["violation"]),
            "execution_ms": round(c["latency_ms"], 1) if c["latency_ms"] is not None else None,
        })
    return {"traces": traces, "session_id": session_id}


@app.get("/traces/stats")
def get_trace_stats(session_id: str = Query(..., description="The browser tab's agent session")):
    """Summary stats for a session."""
    calls = _tool_records(session_id)
    latencies = [c["latency_ms"] for c in calls if c["latency_ms"] is not None]
    return {
        "total": len(calls),
        "allowed": sum(1 for c in calls if c["result"] not in _BLOCKED_RESULTS),
        "blocked": sum(1 for c in calls if c["result"] in _BLOCKED_RESULTS),
        "avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "tools_used": list(dict.fromkeys(_short(c["tool"]) for c in calls)),
    }


@app.get("/traces/config")
def get_trace_config(session_id: str = Query(..., description="The browser tab's agent session")):
    """The agent's effective policy, and which prerequisites this session has satisfied."""
    platform = _platform()
    policy = platform.describe_agent(AGENT)
    return {
        "policy_name": POLICY_LABEL,
        "policy_description": policy["description"],
        "agent_id": policy["name"],
        "strictness": policy["strictness"],
        "tools": policy["tools"],
        "sequences": policy["sequences"],
        "sequence_state": platform.session_prerequisites(session_id, AGENT),
        "settings": policy["settings"],
    }


# GET too: the UI's export button is a plain link.
@app.api_route("/traces/export", methods=["GET", "POST"])
def export_traces(session_id: str = Query(..., description="The browser tab's agent session")):
    """Export a session's trace as downloadable JSON."""
    payload = {
        "session_id": session_id,
        "policy": POLICY_LABEL,
        "traces": [
            {
                "timestamp": c["timestamp"],
                "agent_id": c["agent"],
                "tool": c["tool"],
                "parameters": c["params"],
                "result": c["result"],
                "violation": c["violation"],
                "correction_message": c["correction_message"],
                "latency_ms": c["latency_ms"],
            }
            for c in _tool_records(session_id)
        ],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f"attachment; filename=anvil-trace-{session_id}.json"},
    )


def _violation_to_rule(violation: str | None) -> str:
    if violation is None:
        return "none"
    mapping = {
        "unknown_agent": "access_control",
        "disallowed_tool": "access_control",
        "cross_app_denied": "access_control",
        "missing_prerequisite": "sequence",
        "injection_detected_request": "injection_scan",
        "injection_detected_response": "injection_scan",
        "schema_violation": "schema_validation",
        "upstream_error": "upstream",
        "upstream_timeout": "upstream",
    }
    return mapping.get(violation, violation)
