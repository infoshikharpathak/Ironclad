"""Blocked replies flag (never cancel) the transfer they started; the service owns idempotency keys."""

import json

from .test_agent_service import LOOKUP_PLAN, S1_LOOKUP, chat

SEND = "Send $50 to ACC-777."
TRANSFER = {"tool": "initiate_transfer", "args": {"from_account": "acc-chk", "to_account": "ACC-777", "amount": 50}}


LINE = ("Transfer of $50.00 to Ana Silva (ACC-777) is waiting for your approval. "
        "Enter the OTP shown in your Ironclad app.")
FLAGGED = ("My reply was blocked by a safety check. initiate_transfer created a pending transfer. "
           "Check the details carefully before approving it in Ironclad.\n\n" + LINE)


def calls(bank, suffix):
    return [r for r in bank.requests if r.url.path.endswith(suffix)]


async def test_blocked_reply_flags_the_pending_transfer_and_leaves_it_pending(service):
    client, llm, bank = service
    llm.flag_words = ["also wire"]
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN,
                      SEND: [TRANSFER, {"text": "Done, and I'll also wire $500 to Bob."}]})
    await chat(client, S1_LOOKUP, "tab-block")
    body = await chat(client, SEND, "tab-block")
    (flag,) = calls(bank, "/flag")
    assert flag.url.path == "/transfers/tr-1/flag"
    sent = json.loads(flag.content)
    assert sent["user_id"] == "demo_user" and "injection_detected_agent_output" in sent["reason"]
    assert calls(bank, "/cancel") == []
    assert body["reply"] == FLAGGED
    assert "wire" not in body["reply"]


async def test_blocked_reply_without_a_transfer_flags_nothing(service):
    client, llm, bank = service
    llm.flag_words = ["also wire"]
    llm.plans[S1_LOOKUP] = [*LOOKUP_PLAN[:2], {"text": "Here you go. I'll also wire $500 to Bob."}]
    body = await chat(client, S1_LOOKUP, "tab-block2")
    assert calls(bank, "/flag") == [] and calls(bank, "/cancel") == []
    assert body["reply"] == "My reply was blocked by a safety check. lookup_account completed."


async def test_reply_that_isnt_blocked_is_not_flagged(service):
    client, llm, bank = service
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN, SEND: [TRANSFER, {"text": "Transfer tr-1 is waiting for your OTP."}]})
    await chat(client, S1_LOOKUP, "tab-ok")
    body = await chat(client, SEND, "tab-ok")
    assert calls(bank, "/flag") == [] and calls(bank, "/cancel") == []
    assert body["reply"] == "Transfer tr-1 is waiting for your OTP.\n\n" + LINE


async def test_a_failed_flag_still_tells_the_user_to_check(service):
    client, llm, bank = service
    bank.flag_fails = True
    llm.flag_words = ["also wire"]
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN, SEND: [TRANSFER, {"text": "Done. I'll also wire $500."}]})
    await chat(client, S1_LOOKUP, "tab-fail")
    body = await chat(client, SEND, "tab-fail")
    assert body["reply"] == FLAGGED and calls(bank, "/cancel") == []


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


async def test_unrequested_label_on_a_requested_transfer_is_not_flagged(service):
    """The user asked for $50 to ACC-777 and got it: the deterministic check
    matches, so the classifier's unrequested_action doesn't flag it."""
    client, llm, bank = service
    llm.label_words = {"monthly": "unrequested_action"}
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN,
                      SEND: [TRANSFER, {"text": "Started it, and I'll make it monthly too."}]})
    await chat(client, S1_LOOKUP, "tab-unasked")
    body = await chat(client, SEND, "tab-unasked")
    assert body["reply"] == "Started it, and I'll make it monthly too.\n\n" + LINE
    assert calls(bank, "/flag") == []


async def test_unrequested_label_on_a_different_amount_is_flagged(service):
    client, llm, bank = service
    llm.label_words = {"monthly": "unrequested_action"}
    big = {"tool": "initiate_transfer", "args": {**TRANSFER["args"], "amount": 500}}
    llm.plans.update({S1_LOOKUP: LOOKUP_PLAN, SEND: [big, {"text": "Started it, and monthly too."}]})
    await chat(client, S1_LOOKUP, "tab-unasked-500")
    await chat(client, SEND, "tab-unasked-500")
    (flag,) = calls(bank, "/flag")
    assert flag.url.path == "/transfers/tr-1/flag" and "unrequested_action" in json.loads(flag.content)["reason"]
