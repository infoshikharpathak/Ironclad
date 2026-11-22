"""Blocked replies cancel the transfer they started; the service owns idempotency keys."""

import json

from .test_agent_service import LOOKUP_PLAN, S1_LOOKUP, chat

SEND = "Send $50 to ACC-777."
TRANSFER = {"tool": "initiate_transfer", "args": {"from_account": "acc-chk", "to_account": "ACC-777", "amount": 50}}


def cancels(bank):
    return [r.url.path for r in bank.requests if r.url.path.endswith("/cancel")]


async def test_blocked_reply_cancels_the_pending_transfer(service):
    client, llm, bank = service
    llm.flag_words = ["also wire"]
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN,
                      SEND: [TRANSFER, {"text": "Done, and I'll also wire $500 to Bob."}]})
    await chat(client, S1_LOOKUP, "tab-block")
    body = await chat(client, SEND, "tab-block")
    assert cancels(bank) == ["/transfers/tr-1/cancel"]
    assert json.loads(bank.requests[-1].content) == {"user_id": "demo_user"}
    assert body["reply"] == ("My reply was blocked by a safety check. initiate_transfer created a pending "
                             "transfer, which has been cancelled.")
    assert "wire" not in body["reply"]


async def test_blocked_reply_without_a_transfer_cancels_nothing(service):
    client, llm, bank = service
    llm.flag_words = ["also wire"]
    llm.plans[S1_LOOKUP] = [*LOOKUP_PLAN[:2], {"text": "Here you go. I'll also wire $500 to Bob."}]
    body = await chat(client, S1_LOOKUP, "tab-block2")
    assert cancels(bank) == []
    assert body["reply"] == "My reply was blocked by a safety check. lookup_account completed."


async def test_reply_that_isnt_blocked_leaves_the_transfer_pending(service):
    client, llm, bank = service
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN, SEND: [TRANSFER, {"text": "Transfer tr-1 is waiting for your OTP."}]})
    await chat(client, S1_LOOKUP, "tab-ok")
    body = await chat(client, SEND, "tab-ok")
    assert cancels(bank) == [] and body["reply"] == "Transfer tr-1 is waiting for your OTP."


async def test_a_failed_cancel_is_told_to_the_user(service):
    client, llm, bank = service
    bank.cancel_fails = True
    llm.flag_words = ["also wire"]
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN, SEND: [TRANSFER, {"text": "Done. I'll also wire $500."}]})
    await chat(client, S1_LOOKUP, "tab-fail")
    body = await chat(client, SEND, "tab-fail")
    assert "couldn't be cancelled automatically: decline it in your app" in body["reply"]


async def test_model_sent_idempotency_key_is_blocked(service):
    client, llm, bank = service
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN,
                      SEND: [{"tool": "initiate_transfer", "args": {**TRANSFER["args"], "idempotency_key": "transfer-12345"}},
                             {"text": "That didn't go through."}]})
    await chat(client, S1_LOOKUP, "tab-key")
    await chat(client, SEND, "tab-key")
    seen = llm.tool_results_seen(SEND)[-1]
    assert seen["correction"]["violation"] == "invalid_params"
    assert "idempotency_key: unknown field" in seen["correction"]["message"]
    assert "/transfers/initiate" not in [r.url.path for r in bank.requests]


async def test_each_transfer_gets_its_own_service_key(service):
    client, llm, bank = service
    second = "Send another $50 to ACC-777."
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN, SEND: [TRANSFER, {"text": "Started."}],
                      second: [TRANSFER, {"text": "Started again."}]})
    await chat(client, S1_LOOKUP, "tab-keys")
    await chat(client, SEND, "tab-keys")
    await chat(client, second, "tab-keys")
    keys = [json.loads(r.content)["idempotency_key"] for r in bank.requests if r.url.path == "/transfers/initiate"]
    assert len(keys) == 2 and keys[0] != keys[1] and all(k.startswith("agent_") for k in keys)
