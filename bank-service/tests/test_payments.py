"""Merchant payments API: identity from the key, payee from the registry,
money only after the user's OTP."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services import merchants

pytestmark = pytest.mark.anyio

PAYER = "acc_demo_user_checking"
FOODDASH_SETTLEMENT = "acc_merchant_fooddash_settlement"


async def issue_key(pool, merchant_id: str) -> str:
    key = merchants.new_key()
    await pool.execute("UPDATE merchants SET api_key_hash = $1 WHERE merchant_id = $2",
                       merchants.hash_key(key), merchant_id)
    return key


def auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def body(**overrides) -> dict:
    b = {"order_ref": "ord-1", "amount": 31.0, "user_id": "demo_user", "channel": "checkout",
         "idempotency_key": "fooddash-ord-1"}
    b.update(overrides)
    return b


@pytest.fixture
async def fooddash(bank):
    client, pool, pushed = bank
    return client, pool, pushed, await issue_key(pool, "fooddash")


async def balance(pool, account_id: str) -> Decimal:
    return await pool.fetchval("SELECT balance FROM accounts WHERE id = $1", account_id)


# ── authentication and merchant status ─────────────────────────────────────

async def test_missing_or_unknown_key_is_401(bank):
    client, pool, _ = bank
    assert (await client.post("/payments/requests", json=body())).status_code == 401
    r = await client.post("/payments/requests", json=body(), headers=auth("mk_not-a-real-key"))
    assert (r.status_code, r.json()["error"]) == (401, "MERCHANT_KEY_INVALID")
    r = await client.post("/payments/requests", json=body(), headers={"Authorization": "Bearer bk_wrong_prefix"})
    assert r.status_code == 401
    # A bad key is a 401 even when the body is also invalid.
    assert (await client.post("/payments/requests", json={"x": 1}, headers=auth("mk_nope"))).status_code == 401


async def test_seeded_merchant_without_a_key_cannot_authenticate(bank):
    client, pool, _ = bank
    assert await pool.fetchval("SELECT api_key_hash FROM merchants WHERE merchant_id = 'quickmart'") is None
    assert (await client.get("/payments/requests/txn_x", headers=auth("mk_"))).status_code == 401


async def test_suspended_merchant_is_403(fooddash):
    client, pool, _, key = fooddash
    await pool.execute("UPDATE merchants SET status = 'suspended' WHERE merchant_id = 'fooddash'")
    r = await client.post("/payments/requests", json=body(), headers=auth(key))
    assert (r.status_code, r.json()["error"]) == (403, "MERCHANT_SUSPENDED")


async def test_agent_channel_refused_for_quickmart(bank):
    client, pool, _ = bank
    key = await issue_key(pool, "quickmart")
    r = await client.post("/payments/requests", json=body(channel="agent", idempotency_key="qm-1"), headers=auth(key))
    assert (r.status_code, r.json()["error"]) == (403, "AGENT_PAYMENTS_NOT_ALLOWED")
    ok = await client.post("/payments/requests", json=body(idempotency_key="qm-2"), headers=auth(key))
    assert ok.status_code == 200 and ok.json()["merchant_display_name"] == "QuickMart"


# ── body validation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("field,value", [
    ("merchant_id", "quickmart"), ("to_account", "ACC-10043-CHK"), ("payee", "bob"),
    ("settlement_account_id", "ACC-10043-CHK"), ("from_account", "acc_demo_user_savings"),
])
async def test_payee_or_account_field_in_body_is_422(fooddash, field, value):
    client, pool, _, key = fooddash
    r = await client.post("/payments/requests", json=body(**{field: value}), headers=auth(key))
    assert (r.status_code, r.json()["error"]) == (422, "PAYEE_NOT_ALLOWED")
    assert r.json()["details"]["fields"] == [field]
    assert await pool.fetchval("SELECT count(*) FROM transactions") == 0


async def test_unknown_fields_and_bad_amounts_are_422(fooddash):
    client, _, _, key = fooddash
    for bad in (body(tip=5), body(amount=0), body(amount=-3), body(amount=1.234), body(channel="phone"),
                {"amount": 5}):
        r = await client.post("/payments/requests", json=bad, headers=auth(key))
        assert r.status_code == 422, (bad, r.text)


async def test_over_the_limit_is_422(fooddash):
    client, _, _, key = fooddash
    r = await client.post("/payments/requests", json=body(amount=200.01), headers=auth(key))
    assert (r.status_code, r.json()["error"]) == (422, "AMOUNT_OVER_LIMIT")
    assert r.json()["details"] == {"amount": 200.01, "limit": 200.0}
    assert (await client.post("/payments/requests", json=body(amount=200), headers=auth(key))).status_code == 200


async def test_insufficient_funds_is_422(fooddash):
    client, pool, _, key = fooddash
    await pool.execute("UPDATE accounts SET balance = 10 WHERE id = $1", PAYER)
    r = await client.post("/payments/requests", json=body(amount=31), headers=auth(key))
    assert (r.status_code, r.json()["error"]) == (422, "INSUFFICIENT_FUNDS")


async def test_unknown_payer_is_404(fooddash):
    client, _, _, key = fooddash
    r = await client.post("/payments/requests", json=body(user_id="nobody"), headers=auth(key))
    assert (r.status_code, r.json()["error"]) == (404, "PAYER_NOT_FOUND")


# ── creating a request ─────────────────────────────────────────────────────

async def test_request_is_a_pending_transfer_to_the_registry_settlement_account(fooddash):
    client, pool, pushed, key = fooddash
    r = await client.post("/payments/requests", json=body(channel="agent"), headers=auth(key))
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {"payment_request_id", "status", "amount", "merchant_display_name", "order_ref", "channel",
                        "expires_at", "created_at", "confirmed_at", "idempotent_replay"}
    assert (out["status"], out["amount"], out["merchant_display_name"], out["order_ref"], out["channel"]) == (
        "pending_otp", 31.0, "FoodDash", "ord-1", "agent")

    row = await pool.fetchrow("SELECT * FROM transactions WHERE id = $1", out["payment_request_id"])
    assert (row["from_account"], row["to_account"]) == (PAYER, FOODDASH_SETTLEMENT)
    assert (row["merchant_id"], row["order_ref"], row["channel"], row["initiated_by"]) == (
        "fooddash", "ord-1", "agent", "merchant_agent")
    assert row["status"] == "pending_otp" and row["otp_hash"]
    assert await balance(pool, PAYER) == Decimal("10000.00")  # nothing moves yet

    ((user, event),) = pushed
    assert user == "demo_user" and event["type"] == "otp_required"
    data = event["data"]
    assert (data["merchant_display_name"], data["order_ref"], data["channel"], data["to_name"]) == (
        "FoodDash", "ord-1", "agent", "FoodDash")


async def test_checkout_channel_is_initiated_by_merchant(fooddash):
    client, pool, _, key = fooddash
    out = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()
    assert await pool.fetchval("SELECT initiated_by FROM transactions WHERE id = $1",
                               out["payment_request_id"]) == "merchant"


async def test_payee_always_comes_from_the_registry(fooddash):
    """Change the registry's settlement account: new requests follow it."""
    client, pool, _, key = fooddash
    await pool.execute("""INSERT INTO accounts (id, user_id, name, account_type, balance, owner_name)
                          VALUES ('acc_fd_new', 'merchant:fooddash', 'FD new', 'checking', 0, 'FoodDash')""")
    await pool.execute("UPDATE merchants SET settlement_account_id = 'acc_fd_new' WHERE merchant_id = 'fooddash'")
    out = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()
    assert await pool.fetchval("SELECT to_account FROM transactions WHERE id = $1",
                               out["payment_request_id"]) == "acc_fd_new"


async def test_otp_never_appears_in_any_merchant_response(fooddash):
    client, pool, pushed, key = fooddash
    created = await client.post("/payments/requests", json=body(), headers=auth(key))
    replay = await client.post("/payments/requests", json=body(), headers=auth(key))
    fetched = await client.get(f"/payments/requests/{created.json()['payment_request_id']}", headers=auth(key))
    code = pushed[0][1]["data"]["otp_code"]
    for resp in (created, replay, fetched):
        assert resp.status_code == 200
        assert not any("otp_code" in k or k == "otp" for k in resp.json())
        assert code not in resp.text


# ── idempotency ────────────────────────────────────────────────────────────

async def test_same_key_same_body_returns_the_existing_request(fooddash):
    client, pool, pushed, key = fooddash
    first = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()
    again = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()
    assert again["payment_request_id"] == first["payment_request_id"] and again["idempotent_replay"] is True
    assert await pool.fetchval("SELECT count(*) FROM transactions") == 1
    assert len(pushed) == 1  # no second OTP


async def test_same_key_different_body_is_409(fooddash):
    client, pool, _, key = fooddash
    first = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()
    r = await client.post("/payments/requests", json=body(amount=32), headers=auth(key))
    assert (r.status_code, r.json()["error"]) == (409, "IDEMPOTENCY_KEY_REUSED")
    assert r.json()["details"]["payment_request_id"] == first["payment_request_id"]


async def test_idempotency_keys_are_per_merchant(bank):
    client, pool, _ = bank
    fd, qm = await issue_key(pool, "fooddash"), await issue_key(pool, "quickmart")
    a = (await client.post("/payments/requests", json=body(), headers=auth(fd))).json()
    b = (await client.post("/payments/requests", json=body(amount=10), headers=auth(qm))).json()
    assert a["payment_request_id"] != b["payment_request_id"] and b["merchant_display_name"] == "QuickMart"


# ── reading requests ───────────────────────────────────────────────────────

async def test_merchant_cannot_read_another_merchants_request(bank):
    client, pool, _ = bank
    fd, qm = await issue_key(pool, "fooddash"), await issue_key(pool, "quickmart")
    pid = (await client.post("/payments/requests", json=body(), headers=auth(fd))).json()["payment_request_id"]
    assert (await client.get(f"/payments/requests/{pid}", headers=auth(fd))).json()["status"] == "pending_otp"
    r = await client.get(f"/payments/requests/{pid}", headers=auth(qm))
    assert (r.status_code, r.json()["error"]) == (404, "PAYMENT_REQUEST_NOT_FOUND")
    # ...nor an ordinary transfer that isn't a payment request
    await pool.execute("""INSERT INTO transactions (id, from_account, to_account, amount, user_id)
                          VALUES ('txn_plain', $1, 'ACC-10043-CHK', 5, 'demo_user')""", PAYER)
    assert (await client.get("/payments/requests/txn_plain", headers=auth(fd))).status_code == 404


# ── confirming, expiry, cancellation ───────────────────────────────────────

async def test_confirmed_payment_moves_money_to_the_settlement_account(fooddash):
    client, pool, pushed, key = fooddash
    pid = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()["payment_request_id"]
    pending = (await client.get("/transfers/pending", params={"user_id": "demo_user"})).json()["transfers"]
    (p,) = pending
    assert (p["transfer_id"], p["merchant_display_name"], p["order_ref"], p["channel"], p["to_name"]) == (
        pid, "FoodDash", "ord-1", "checkout", "FoodDash")
    r = await client.post(f"/transfers/{pid}/confirm", json={"user_id": "demo_user", "otp_code": p["otp_code"]})
    assert r.status_code == 200, r.text
    assert await balance(pool, PAYER) == Decimal("9969.00")
    assert await balance(pool, FOODDASH_SETTLEMENT) == Decimal("31.00")
    got = (await client.get(f"/payments/requests/{pid}", headers=auth(key))).json()
    assert got["status"] == "confirmed" and got["confirmed_at"]


async def test_declined_payment_is_cancelled(fooddash):
    client, pool, _, key = fooddash
    pid = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()["payment_request_id"]
    await client.post(f"/transfers/{pid}/cancel", json={"user_id": "demo_user"})
    assert (await client.get(f"/payments/requests/{pid}", headers=auth(key))).json()["status"] == "cancelled"
    assert await balance(pool, FOODDASH_SETTLEMENT) == 0


async def test_expired_payment_reads_as_expired_and_is_closed(fooddash):
    client, pool, pushed, key = fooddash
    pid = (await client.post("/payments/requests", json=body(), headers=auth(key))).json()["payment_request_id"]
    await pool.execute("UPDATE transactions SET otp_expires_at = $1 WHERE id = $2",
                       datetime.now(timezone.utc) - timedelta(seconds=1), pid)
    assert (await client.get(f"/payments/requests/{pid}", headers=auth(key))).json()["status"] == "expired"
    row = await pool.fetchrow("SELECT status, closed_reason FROM transactions WHERE id = $1", pid)
    assert (row["status"], row["closed_reason"]) == ("cancelled", "expired")
    assert pushed[-1][1] == {"type": "transfer_cancelled", "data": {"transfer_id": pid, "reason": "OTP expired"}}
    # still expired on the next read, and the OTP can no longer confirm it
    assert (await client.get(f"/payments/requests/{pid}", headers=auth(key))).json()["status"] == "expired"
    r = await client.post(f"/transfers/{pid}/confirm", json={"user_id": "demo_user", "otp_code": "000000"})
    assert r.json()["error"] == "TRANSFER_NOT_PENDING"
