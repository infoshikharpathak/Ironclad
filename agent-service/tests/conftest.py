"""Stubbed LLM and bank for agent-service tests. Anvil, Agent Forge and
bastion are real; only the model and the bank's HTTP API are fake."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import httpx
import pytest
from bastion.classifier import CLASSIFIER_PROMPT
from openai.types.chat import ChatCompletion

os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-tests")
os.environ.pop("OPENAI_MODEL", None)


def _completion(message: dict, finish: str) -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "c", "object": "chat.completion", "created": 0, "model": "stub",
        "choices": [{"index": 0, "finish_reason": finish, "message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


class StubLLM:
    """OpenAI-compatible stub. *plans* maps a user message to the steps the
    model takes for it: {"tool": name, "args": {...}} or {"text": "..."}.
    The step is picked from the conversation the agent actually sent (number
    of assistant turns since that user message), so concurrent sessions
    never interfere, and each request is recorded for history checks."""

    def __init__(self, plans: dict[str, list[dict]]):
        self.plans = plans
        self.requests: list[list] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        msgs = kwargs["messages"]
        if msgs[0]["content"] == CLASSIFIER_PROMPT:  # Anvil's injection scan, via the SDK
            return _completion({"role": "assistant", "content": '{"injection": false}'}, "stop")
        self.requests.append(msgs)
        last_user = max(i for i, m in enumerate(msgs) if _role(m) == "user")
        user_text = _content(msgs[last_user])
        done = sum(1 for m in msgs[last_user + 1:] if _role(m) == "assistant")
        step = self.plans[user_text][done]
        if "tool" in step:
            return _completion({"role": "assistant", "content": None, "tool_calls": [{
                "id": f"call_{done}", "type": "function",
                "function": {"name": step["tool"], "arguments": json.dumps(step.get("args", {}))},
            }]}, "tool_calls")
        return _completion({"role": "assistant", "content": step["text"]}, "stop")

    def tool_results_seen(self, user_text: str) -> list[dict]:
        """Tool results the model was given while answering *user_text*."""
        out = []
        for msgs in self.requests:
            idx = [i for i, m in enumerate(msgs) if _role(m) == "user" and _content(m) == user_text]
            if not idx:
                continue
            for m in msgs[idx[-1] + 1:]:
                if _role(m) == "tool":
                    r = json.loads(m["content"])
                    if r not in out:
                        out.append(r)
        return out


def _role(m):
    return m.get("role") if isinstance(m, dict) else getattr(m, "role", None)


def _content(m):
    return m.get("content") if isinstance(m, dict) else getattr(m, "content", None)


class StubBank:
    """The bank-service endpoints the agent's tools hit."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.leak_otp = False  # behave like an old bank that returned the code
        self.memo = "Lunch"     # memo on the incoming payment get_transactions returns

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/accounts":
            return httpx.Response(200, json={"accounts": [
                {"id": "acc-chk", "name": "Everyday Checking", "account_type": "checking", "balance": 2400.0, "currency": "USD"},
            ]})
        if path.endswith("/transactions"):
            return httpx.Response(200, json={"limit": 20, "offset": 0, "transactions": [
                {"id": "tx-1", "from_account": "ACC-10043-CHK", "to_account": "acc-chk", "amount": 1.0,
                 "status": "confirmed", "description": self.memo, "initiated_by": "user"},
            ]})
        if path.startswith("/directory/lookup/"):
            number = path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"account_number": number, "owner_name": "Ana Silva",
                                             "account_type": "checking", "currency": "USD"})
        if path == "/transfers/initiate":
            body = json.loads(request.content)
            out = {"transfer_id": "tr-1", "status": "pending_otp", "amount": body["amount"]}
            if self.leak_otp:
                out["otp_code"] = "482913"
            return httpx.Response(200, json=out)
        return httpx.Response(404, json={"detail": f"stub bank has no {path}"})

    def paths(self):
        return [r.url.path for r in self.requests]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FORGE_DB_PATH", str(tmp_path / "forge.db"))
    monkeypatch.chdir(tmp_path)  # local traces land here
    yield
    from agent_forge.tools import _REGISTRY, sources

    for name in [n for n, fn in _REGISTRY.items() if getattr(fn, "_tool_source", None) is not None]:
        _REGISTRY.pop(name)
    sources._SOURCE_TOOLS.clear()


@pytest.fixture
async def service():
    """(client, llm, bank): the real FastAPI app on a Platform wired to stubs."""
    import app.main as main

    llm, bank = StubLLM({}), StubBank()
    platform = main.build_platform(openai_client=llm, http_transport=httpx.MockTransport(bank))
    await platform.start()
    main.app.state.platform = platform
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        yield client, llm, bank
    await platform.close()
