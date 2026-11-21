"""Ironclad Agent Service: the banking assistant, on the anvil-forge SDK.

anvil-forge runs the agent (Agent Forge) under Anvil governance: the
agent, its tools and its policy all come from anvil-ironclad.yaml. This
service only adds what is Ironclad-specific: the signed-in user's ID on
every tool call, and the HTTP shapes the web UI expects.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

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

from anvil_forge import Platform, load_config  # noqa: E402

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
        params.setdefault("idempotency_key", f"agent_{uuid.uuid4().hex[:12]}")
    return params


def build_platform() -> Platform:
    raw = yaml.safe_load(open(CONFIG_PATH))
    if os.getenv("OPENAI_MODEL"):  # same override the service always had
        raw["agents"][AGENT_ID]["model"] = os.environ["OPENAI_MODEL"]
    return Platform(load_config(raw), app=APP, prepare_tool_call=prepare_tool_call)


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
    try:
        reply = await _platform().run_agent(AGENT, req.message, session_id=req.session_id)
    except Exception as exc:
        logger.exception("Agent error")
        return ChatResponse(reply=f"I encountered an error: {exc}", tool_calls=[])
    return ChatResponse(reply=reply.content, tool_calls=[_tool_call_info(c) for c in reply.trace.get("tool_calls", [])])


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
            "decision": "blocked" if result == "blocked" else "allowed",
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
        "allowed": sum(1 for c in calls if c["result"] in ("success", "response_withheld")),
        "blocked": sum(1 for c in calls if c["result"] == "blocked"),
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
