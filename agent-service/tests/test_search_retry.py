"""An empty policy search is retried once with the user's own words, by the
service, before the model sees the result."""

import json

from .conftest import PUBLIC_KEY
from .test_agent_service import chat

ASK = "Is there a foreign transaction fee?"


def searches(bank):
    return [r for r in bank.requests if r.url.path == "/policies/search"]


async def test_empty_search_then_successful_retry_gives_the_model_the_retry(service):
    client, llm, bank = service
    bank.empty_queries = {"foreign fee"}
    llm.plans[ASK] = [{"tool": "search_policies", "args": {"q": "foreign fee", "top_k": 3}}, {"text": "No fee."}]
    body = await chat(client, ASK, "tab-retry")
    first, second = searches(bank)
    assert first.url.params["q"] == "foreign fee" and second.url.params["q"] == ASK
    assert second.url.params["top_k"] == "3"
    (seen,) = llm.tool_results_seen(ASK)
    assert seen["data"]["query"] == ASK and seen["data"]["results"]
    calls = [c for c in body["tool_calls"] if c["tool"] == "search_policies"]
    assert len(calls) == 2
    traces = (await client.get("/traces/export", params={"session_id": "tab-retry"})).json()["traces"]
    assert len([t for t in traces if t["tool"].endswith("search_policies")]) == 2


async def test_both_empty_gives_the_empty_result(service):
    client, llm, bank = service
    bank.empty_queries = {"personal loan", "Can I get a personal loan?"}
    msg = "Can I get a personal loan?"
    llm.plans[msg] = [{"tool": "search_policies", "args": {"q": "personal loan"}}, {"text": "Not covered."}]
    await chat(client, msg, "tab-retry-empty")
    assert len(searches(bank)) == 2
    (seen,) = llm.tool_results_seen(msg)
    assert seen["data"]["query"] == "personal loan" and seen["data"]["results"] == []


async def test_query_identical_to_the_message_is_not_retried(service):
    client, llm, bank = service
    bank.empty_queries = {ASK}
    llm.plans[ASK] = [{"tool": "search_policies", "args": {"q": ASK}}, {"text": "Not covered."}]
    await chat(client, ASK, "tab-retry-same")
    assert len(searches(bank)) == 1


async def test_retry_uses_the_same_key_and_no_level(service):
    client, llm, bank = service
    bank.empty_queries = {"foreign fee"}
    llm.plans[ASK] = [{"tool": "search_policies", "args": {"q": "foreign fee"}}, {"text": "No fee."}]
    await chat(client, ASK, "tab-retry-key")
    for r in searches(bank):
        assert r.headers["authorization"] == f"Bearer {PUBLIC_KEY}"
        assert set(r.url.params) <= {"q", "top_k"}


async def test_retry_is_marked_in_the_trace(service):
    import app.main as main

    client, llm, bank = service
    bank.empty_queries = {"foreign fee"}
    llm.plans[ASK] = [{"tool": "search_policies", "args": {"q": "foreign fee"}}, {"text": "No fee."}]
    resp = await main._platform().run_agent(main.AGENT, ASK, session_id="direct-retry")
    calls = [c for c in resp.trace["tool_calls"] if c["tool"] == "search_policies"]
    assert [c.get("retried_with_user_text") for c in calls] == [None, True]
    assert calls[1]["original_q"] == "foreign fee"
    assert json.dumps(calls[1]["response"]).count("transfer-limits") >= 1
