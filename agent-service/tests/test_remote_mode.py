"""BASTION_URL + BASTION_KEY: the agent runs on the control plane's bundle."""

import copy
import hashlib
import json
from pathlib import Path

import httpx
import pytest
import yaml

from .conftest import StubBank, StubLLM

CONFIG = yaml.safe_load((Path(__file__).resolve().parents[2] / "anvil-ironclad.yaml").read_text())
KEY = "bk_" + "k" * 43


class FakeBastion:
    """The control plane's GET /v1/sdk/bundle, with ETags."""

    def __init__(self, bundle):
        self.publish(bundle, 1)

    def publish(self, bundle, revision):
        self.bundle, self.revision = copy.deepcopy(bundle), revision
        self.etag = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()

    def __call__(self, request):
        if request.headers.get("authorization") != f"Bearer {KEY}":
            return httpx.Response(401, json={"detail": "bad key"})
        if request.headers.get("if-none-match", "").strip('"') == self.etag:
            return httpx.Response(304)
        return httpx.Response(200, json={"app": "ironclad", "revision": self.revision, "etag": self.etag,
                                         "bundle": self.bundle})


@pytest.fixture
async def remote(monkeypatch, tmp_path):
    import app.main as main

    monkeypatch.setenv("BASTION_URL", "http://bastion.test")
    monkeypatch.setenv("BASTION_KEY", KEY)
    monkeypatch.setenv("BASTION_REFRESH_SECONDS", "0")  # tests refresh explicitly
    forge, llm, bank = FakeBastion(CONFIG), StubLLM({}), StubBank()
    platform = main.build_platform(openai_client=llm, http_transport=httpx.MockTransport(bank),
                                   service_transport=httpx.MockTransport(forge), cache_dir=tmp_path,
                                   dashboard=False)  # FakeBastion has no /v1/traces
    await platform.start()
    main.app.state.platform = platform
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://agent") as client:
        yield client, platform, forge, llm
    await platform.close()


async def test_remote_mode_runs_on_the_service_bundle(remote):
    client, platform, _, llm = remote
    assert platform.bundle_revision == 1
    llm.plans["hi"] = [{"text": "Hello from the bundle."}]
    r = await client.post("/agent/chat", json={"message": "hi", "session_id": "tab"})
    assert r.json()["reply"] == "Hello from the bundle."
    cfg = (await client.get("/traces/config", params={"session_id": "tab"})).json()
    assert cfg["agent_id"] == "banking_agent" and cfg["strictness"] == "strict"


async def test_prompt_edit_in_the_service_applies_without_restart(remote):
    client, platform, forge, llm = remote
    llm.plans.update({"first": [{"text": "one"}], "second": [{"text": "two"}]})
    await client.post("/agent/chat", json={"message": "first", "session_id": "tab"})
    old_prompt = llm.requests[-1][0]["content"]

    edited = copy.deepcopy(CONFIG)
    edited["agents"]["ironclad.banking_agent"].update(instructions="You are Ironclad's assistant. Be brief.",
                                                      prompt_version="v2")
    forge.publish(edited, 2)
    assert await platform.refresh() is True
    await client.post("/agent/chat", json={"message": "second", "session_id": "tab"})
    sent = llm.requests[-1]
    assert sent[0]["content"] == "You are Ironclad's assistant. Be brief." != old_prompt
    assert any(isinstance(m, dict) and m.get("content") == "first" for m in sent)  # same conversation
    assert platform.describe_agent("banking_agent")["prompt_version"] == "v2"


def test_key_for_another_app_is_refused(monkeypatch, tmp_path):
    import app.main as main

    other = copy.deepcopy(CONFIG)
    forge = FakeBastion(other)
    forge_resp = forge.__call__

    def as_other_app(request):
        resp = forge_resp(request)
        body = resp.json()
        body["app"] = "notify"
        body["bundle"] = {"apps": {"notify": {"tools": {}}}}
        return httpx.Response(200, json=body)

    monkeypatch.setenv("BASTION_URL", "http://bastion.test")
    monkeypatch.setenv("BASTION_KEY", KEY)
    with pytest.raises(RuntimeError, match="belongs to app 'notify'"):
        main.build_platform(service_transport=httpx.MockTransport(as_other_app), cache_dir=tmp_path)


def test_without_the_env_vars_it_is_local_mode(monkeypatch):
    import app.main as main

    monkeypatch.delenv("BASTION_URL", raising=False)
    monkeypatch.delenv("BASTION_KEY", raising=False)
    platform = main.build_platform()
    assert platform.bundle_revision is None and platform.app == "ironclad"


async def test_ironclad_base_url_points_tools_at_the_bank(monkeypatch):
    """docker-compose sets IRONCLAD_BASE_URL=http://bank-service:8001."""
    import httpx

    import app.main as main

    from .conftest import StubBank, StubLLM

    monkeypatch.delenv("BASTION_URL", raising=False)
    monkeypatch.delenv("BASTION_KEY", raising=False)
    monkeypatch.setenv("IRONCLAD_BASE_URL", "http://bank-service:8001/")
    llm = StubLLM({"Balances?": [{"tool": "get_accounts", "args": {}}, {"text": "You have $2,400."}]})
    bank = StubBank()
    platform = main.build_platform(openai_client=llm, http_transport=httpx.MockTransport(bank))
    await platform.run_agent("banking_agent", "Balances?")
    await platform.close()
    (req,) = bank.requests
    assert (req.url.host, req.url.port, req.url.path) == ("bank-service", 8001, "/accounts")


def test_ironclad_base_url_is_ignored_in_remote_mode_with_a_warning(monkeypatch, tmp_path, caplog):
    import app.main as main

    monkeypatch.setenv("IRONCLAD_BASE_URL", "http://bank-service:8001")
    monkeypatch.setenv("BASTION_URL", "http://bastion.test")
    monkeypatch.setenv("BASTION_KEY", KEY)
    service = FakeBastion(CONFIG)
    with caplog.at_level("WARNING"):
        platform = main.build_platform(service_transport=httpx.MockTransport(service), cache_dir=tmp_path,
                                       dashboard=False)
    assert "IRONCLAD_BASE_URL is ignored in remote mode" in caplog.text
    assert platform.config.platform.apps["ironclad"]["base_url"] != "http://bank-service:8001"
