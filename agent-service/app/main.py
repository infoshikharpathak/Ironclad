"""Ironclad Agent Service — AI banking assistant powered by agent-forge + Anvil.

Uses agent-forge's OpenAIAgent for the LLM conversation loop and routes
every tool call through Anvil for policy enforcement.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# In Docker, anvil and agent-forge are pip-installed.
# For local dev, fall back to sibling project directories.
try:
    import anvil  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../anvil/src"))
try:
    import agent_forge  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../agent-forge/src"))

from dotenv import load_dotenv
load_dotenv()
# Local dev fallback: load .env from agent-forge if it exists
_forge_env = os.path.join(os.path.dirname(__file__), "../../../agent-forge/.env")
if os.path.exists(_forge_env):
    load_dotenv(_forge_env)

from agent_forge.backends.openai import OpenAIAgent
from openai import AsyncOpenAI
from anvil import Anvil
from anvil.models import ToolResponse
from anvil.namespaces import short_name

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("ironclad-agent")

# ── Config ───────────────────────────────────────────────────────────────────

# docker-compose sets ANVIL_CONFIG_PATH (the yaml is mounted at /app/anvil-ironclad.yaml).
# Local dev falls back to the repo-root file next to agent-service/.
ANVIL_CONFIG_PATH = os.environ.get("ANVIL_CONFIG_PATH") or os.path.join(
    os.path.dirname(__file__), "../../anvil-ironclad.yaml"
)
ANVIL_POLICY = "ironclad-banking"
ANVIL_APP = "ironclad"
ANVIL_AGENT_ID = "ironclad.banking_agent"
BANK_USER_ID = "demo_user"

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]

SYSTEM_PROMPT = """\
You are the Ironclad Bank AI Assistant. You help the user manage their bank accounts.

You can:
- Check account balances (get_accounts)
- View transaction history (get_transactions)
- Look up people to send money to (list_directory, lookup_account)
- Initiate transfers (initiate_transfer) — these require OTP confirmation from the user
- Check transfer status (get_transfer_status)

Important rules:
- The user is "demo_user". Always use this user_id.
- Before initiating a transfer, ALWAYS call get_accounts first to see the user's accounts, then lookup_account to verify the recipient. Anvil governance enforces this — skipping these steps will block the transfer.
- You can NEVER confirm an OTP. After initiating a transfer, tell the user to check the OTP modal in the bank dashboard to confirm it.
- When initiating transfers, always set initiated_by to "agent".
- Be concise and helpful. Format currency amounts properly.
- If a tool call is blocked by governance, explain what happened and what steps are needed.
"""

# ── Tool definitions (OpenAI function-calling format) ────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_accounts",
            "description": "List all accounts for the user. Returns account IDs, names, types, and balances.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions",
            "description": "List recent transactions for a specific account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "The account ID"},
                    "limit": {"type": "integer", "description": "Max transactions (1-100, default 20)"},
                },
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_account",
            "description": "Look up an account by its public number. Returns owner name and type. Use to verify a recipient before transfer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_number": {"type": "string", "description": "Public account number (e.g. ACC-10042-CHK)"},
                },
                "required": ["account_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List all publicly discoverable accounts — people the user can send money to.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transfer_status",
            "description": "Check the current status of a transfer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transfer_id": {"type": "string", "description": "The transfer ID"},
                },
                "required": ["transfer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "initiate_transfer",
            "description": (
                "Initiate a money transfer. Creates a pending transfer requiring OTP from the user. "
                "You MUST call get_accounts and lookup_account first (Anvil governance requires it)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_account": {"type": "string", "description": "Source account ID"},
                    "to_account": {"type": "string", "description": "Destination account ID or public number"},
                    "amount": {"type": "number", "description": "Amount in USD"},
                    "description": {"type": "string", "description": "Transfer memo"},
                },
                "required": ["from_account", "to_account", "amount"],
            },
        },
    },
]

# ── Anvil governance layer ───────────────────────────────────────────────────

_anvil: Anvil | None = None


def _get_anvil() -> Anvil:
    global _anvil
    if _anvil is None:
        _anvil = Anvil.from_config(ANVIL_CONFIG_PATH, policy=ANVIL_POLICY, app=ANVIL_APP)
        logger.info("Anvil session: %s (policy: %s)", _anvil.session_id, ANVIL_POLICY)
    return _anvil


# Captured tool calls for the current request — request-scoped via ContextVar
_captured_calls_var: ContextVar[list[dict[str, Any]]] = ContextVar("captured_calls", default=[])


async def _anvil_execute(tool_name: str, **kwargs: Any) -> dict:
    """Route a tool call through Anvil and capture it for the response."""
    anvil = _get_anvil()
    params = dict(kwargs)

    if tool_name in ("get_accounts", "get_transactions", "get_transfer_status"):
        params.setdefault("user_id", BANK_USER_ID)

    if tool_name == "initiate_transfer":
        params.setdefault("user_id", BANK_USER_ID)
        params.setdefault("initiated_by", "agent")
        params.setdefault("idempotency_key", f"agent_{uuid.uuid4().hex[:12]}")

    logger.info("Tool call: %s(%s)", tool_name, params)
    resp: ToolResponse = await anvil.execute(ANVIL_AGENT_ID, tool_name, params)

    if resp.success:
        result = resp.data or {}
        _captured_calls_var.get().append({"tool": tool_name, "input": kwargs, "result": result, "blocked": False})
        return result

    error_msg = resp.correction.message if resp.correction else "Tool call blocked by governance."
    result = {"error": error_msg, "blocked": True}
    _captured_calls_var.get().append({"tool": tool_name, "input": kwargs, "result": result, "blocked": True})
    return result


def _make_handler(tool_name: str):
    """Create an async handler for a specific tool that routes through Anvil."""
    async def handler(**kwargs: Any) -> dict:
        return await _anvil_execute(tool_name, **kwargs)
    return handler


# ── Agent (single-user demo) ────────────────────────────────────────────────

_agent: OpenAIAgent | None = None


def _get_agent() -> OpenAIAgent:
    global _agent
    if _agent is None:
        client = AsyncOpenAI()
        tool_names = [t["function"]["name"] for t in TOOLS]
        _agent = OpenAIAgent(
            agent_id="ironclad-banking-agent",
            name="Ironclad Assistant",
            role="banking_assistant",
            client=client,
            system_message=SYSTEM_PROMPT,
            model=MODEL,
            tools=TOOLS,
            tool_handlers={name: _make_handler(name) for name in tool_names},
        )
        logger.info("Agent created (model=%s, tools=%s)", MODEL, tool_names)
    return _agent


# ── FastAPI app ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_anvil()
    _get_agent()
    logger.info("Ironclad Agent Service ready (model=%s)", MODEL)
    yield
    logger.info("Shutting down")
    agent = _get_agent()
    await agent.close()
    if _anvil:
        await _anvil.end_session()


app = FastAPI(title="Ironclad Agent Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ToolCallInfo(BaseModel):
    tool: str
    input: dict[str, Any]
    result: dict[str, Any]
    blocked: bool = False


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallInfo] = []


@app.get("/health")
def health():
    return {"status": "ok", "anvil_session": _anvil.session_id if _anvil else None}


@app.post("/agent/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    agent = _get_agent()
    calls: list[dict[str, Any]] = []
    _captured_calls_var.set(calls)

    try:
        result = await agent.run(req.message)
        return ChatResponse(
            reply=result.content,
            tool_calls=[ToolCallInfo(**c) for c in calls],
        )
    except Exception as exc:
        logger.exception("Agent error")
        return ChatResponse(
            reply=f"I encountered an error: {exc}",
            tool_calls=[ToolCallInfo(**c) for c in calls],
        )


@app.post("/agent/reset")
async def reset_agent():
    global _anvil
    agent = _get_agent()
    agent.reset_conversation()
    if _anvil:
        await _anvil.end_session()
    _anvil = None
    _get_anvil()
    return {"status": "ok", "message": "Conversation and Anvil session reset."}


# ── Trace API ────────────────────────────────────────────────────────────────

@app.get("/traces")
def get_traces():
    """Return all Anvil trace events for the current session."""
    anvil = _get_anvil()
    calls = anvil.call_log.calls_for(anvil.session_id, ANVIL_AGENT_ID)
    traces = []
    for i, c in enumerate(calls):
        traces.append({
            "id": f"trace_{i:03d}",
            "timestamp": c.timestamp,
            "agent_id": short_name(c.agent),
            "tool": short_name(c.tool),
            "parameters": c.params,
            "decision": "blocked" if c.result.value == "blocked" else "allowed",
            "result": c.result.value,
            "reason": c.correction_message or ("Allowed by policy" if c.result.value == "success" else "Response withheld"),
            "violation": c.violation.value if c.violation else None,
            "policy_rule": _violation_to_rule(c.violation.value if c.violation else None),
            "execution_ms": round(c.latency_ms, 1) if c.latency_ms is not None else None,
        })
    return {"traces": traces, "session_id": anvil.session_id}


@app.get("/traces/stats")
def get_trace_stats():
    """Summary stats for the current Anvil session."""
    anvil = _get_anvil()
    calls = anvil.call_log.calls_for(anvil.session_id, ANVIL_AGENT_ID)
    total = len(calls)
    allowed = sum(1 for c in calls if c.result.value in ("success", "response_withheld"))
    blocked = sum(1 for c in calls if c.result.value == "blocked")
    tools_used = list(dict.fromkeys(short_name(c.tool) for c in calls))
    latencies = [c.latency_ms for c in calls if c.latency_ms is not None]
    avg_ms = round(sum(latencies) / len(latencies), 1) if latencies else 0
    return {
        "total": total,
        "allowed": allowed,
        "blocked": blocked,
        "avg_ms": avg_ms,
        "tools_used": tools_used,
    }


@app.get("/traces/config")
def get_trace_config():
    """Return the active Anvil policy configuration for display."""
    anvil = _get_anvil()
    policy = anvil.config.policies.get(anvil.policy_name)
    if not policy:
        return {"policy": None}

    # Resolved policy: tool references are full "ironclad.x" IDs here.
    agent_policy = anvil.policy_engine.agent_policy(ANVIL_AGENT_ID)
    tools_config = []
    for name, tool in anvil.config.tools.items():
        if agent_policy and name in agent_policy.allowed_tools:
            trust = "trusted"
            if agent_policy.trust_overrides.get(name):
                trust = agent_policy.trust_overrides[name]
            elif tool.trust:
                trust = tool.trust
            tools_config.append({
                "name": short_name(name),
                "trust": trust,
                "injection_scanning": tool.injection_scanning,
                "description": tool.description,
            })

    sequences = []
    if agent_policy:
        for seq in agent_policy.sequences:
            sequences.append({
                "before": short_name(seq.before),
                "requires": [short_name(r) for r in seq.requires],
                "match_fields": seq.match_fields,
            })

    satisfied_tools = [short_name(t) for t in anvil.call_log.history_names(anvil.session_id, ANVIL_AGENT_ID)]

    return {
        "policy_name": anvil.policy_name,
        "policy_description": policy.description,
        "agent_id": short_name(ANVIL_AGENT_ID),
        "strictness": agent_policy.strictness if agent_policy else "strict",
        "tools": tools_config,
        "sequences": sequences,
        "sequence_state": satisfied_tools,
        "settings": {
            "injection_scanning": anvil.config.settings.injection_scanning,
            "default_trust": anvil.config.settings.default_trust,
            "session_ttl": anvil.config.settings.session_ttl,
        },
    }


@app.post("/traces/export")
def export_traces():
    """Export the full trace as downloadable JSON."""
    anvil = _get_anvil()
    calls = anvil.call_log.calls_for(anvil.session_id, ANVIL_AGENT_ID)
    from fastapi.responses import JSONResponse
    payload = {
        "session_id": anvil.session_id,
        "policy": anvil.policy_name,
        "traces": [
            {
                "timestamp": c.timestamp,
                "agent_id": c.agent,
                "tool": c.tool,
                "parameters": c.params,
                "result": c.result.value,
                "violation": c.violation.value if c.violation else None,
                "correction_message": c.correction_message,
                "latency_ms": c.latency_ms,
            }
            for c in calls
        ],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f"attachment; filename=anvil-trace-{anvil.session_id}.json"},
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
