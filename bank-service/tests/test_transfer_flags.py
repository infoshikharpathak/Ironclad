"""Output-scan flags: a flagged transfer stays pending, is marked in
/transfers/pending and the push, and can still be confirmed or declined."""

import pytest

from .test_payments import auth, body, fooddash  # noqa: F401  (fixture)

pytestmark = pytest.mark.anyio

CHK, BOB = "acc_demo_user_checking", "ACC-10043-CHK"
REASON = "injection_detected_agent_output: reply offered to act unasked"


async def start(client, amount=25):
    r = await client.post("/transfers/initiate", json={
        "user_id": "demo_user", "from_account": CHK, "to_account": BOB, "amount": amount, "initiated_by": "agent"})
    assert r.status_code == 200, r.text
    return r.json()["transfer_id"]


async def pending(client):
    return {p["transfer_id"]: p for p in
            (await client.get("/transfers/pending", params={"user_id": "demo_user"})).json()["transfers"]}


async def test_flag_keeps_it_pending_and_shows_in_pending_and_the_push(bank):
    client, pool, pushed = bank
    tid = await start(client)
    r = await client.post(f"/transfers/{tid}/flag", json={"user_id": "demo_user", "reason": REASON})
    assert r.status_code == 200, r.text
    assert r.json() == {"transfer_id": tid, "status": "pending_otp", "flagged_by_output_scan": True}
    p = (await pending(client))[tid]
    assert p["flagged_by_output_scan"] is True and p["flag_reason"] == REASON
    assert ("demo_user", {"type": "transfer_flagged", "data": {
        "transfer_id": tid, "flagged_by_output_scan": True, "flag_reason": REASON}}) in pushed


async def test_unflagged_transfer_has_no_flag(bank):
    client, _, pushed = bank
    tid = await start(client)
    p = (await pending(client))[tid]
    assert p["flagged_by_output_scan"] is False and p["flag_reason"] is None
    assert not [e for _, e in pushed if e["type"] == "transfer_flagged"]


async def test_flagged_transfer_can_still_be_confirmed_with_the_otp(bank):
    client, _, _ = bank
    tid = await start(client)
    await client.post(f"/transfers/{tid}/flag", json={"user_id": "demo_user", "reason": REASON})
    otp = (await pending(client))[tid]["otp_code"]
    r = await client.post(f"/transfers/{tid}/confirm", json={"user_id": "demo_user", "otp_code": otp})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"


async def test_flagged_transfer_can_still_be_declined(bank):
    client, _, _ = bank
    tid = await start(client)
    await client.post(f"/transfers/{tid}/flag", json={"user_id": "demo_user", "reason": REASON})
    r = await client.post(f"/transfers/{tid}/cancel", json={"user_id": "demo_user"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert tid not in await pending(client)


async def test_flag_needs_the_owner_and_a_pending_transfer(bank):
    client, _, _ = bank
    tid = await start(client)
    r = await client.post(f"/transfers/{tid}/flag", json={"user_id": "someone_else", "reason": REASON})
    assert r.status_code == 403
    await client.post(f"/transfers/{tid}/cancel", json={"user_id": "demo_user"})
    r = await client.post(f"/transfers/{tid}/flag", json={"user_id": "demo_user", "reason": REASON})
    assert (r.status_code, r.json()["error"]) == (422, "TRANSFER_NOT_PENDING")
    r = await client.post("/transfers/txn_nope/flag", json={"user_id": "demo_user", "reason": REASON})
    assert r.status_code == 404


async def test_merchant_flags_its_own_payment_request(fooddash):  # noqa: F811
    client, _, pushed, key = fooddash
    pid = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()["payment_request_id"]
    r = await client.post(f"/payments/requests/{pid}/flag", json={"reason": REASON}, headers=auth(key))
    assert r.status_code == 200, r.text
    assert r.json()["flagged_by_output_scan"] is True
    assert (await pending(client))[pid]["flagged_by_output_scan"] is True
    assert any(e["type"] == "transfer_flagged" and e["data"]["transfer_id"] == pid for _, e in pushed)
    r = await client.post(f"/payments/requests/{pid}/flag", json={"reason": REASON})
    assert r.status_code == 401
