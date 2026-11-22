"""Person-to-person limits: $5,000 per transfer, $10,000 per UTC day."""

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.anyio

CHK, SAV, BOB = "acc_demo_user_checking", "acc_demo_user_savings", "ACC-10043-CHK"


@pytest.fixture
async def rich(bank):
    client, pool, pushed = bank
    await pool.execute("UPDATE accounts SET balance = 50000 WHERE id = $1", CHK)
    return client, pool


async def send(client, amount, to=BOB, key=None):
    body = {"user_id": "demo_user", "from_account": CHK, "to_account": to, "amount": amount}
    if key:
        body["idempotency_key"] = key
    return await client.post("/transfers/initiate", json=body)


async def test_per_transfer_limit(rich):
    client, _ = rich
    assert (await send(client, 5000)).status_code == 200
    r = await send(client, 5000.01)
    assert (r.status_code, r.json()["error"]) == (422, "LIMIT_PER_TRANSFER")
    assert r.json()["details"] == {"amount": 5000.01, "limit": 5000.0}


async def test_own_accounts_are_not_limited(rich):
    client, _ = rich
    assert (await send(client, 20000, to=SAV)).status_code == 200


async def test_daily_limit_across_transfers(rich):
    client, _ = rich
    for amount in (4000, 4000, 2000):  # exactly $10,000
        assert (await send(client, amount)).status_code == 200
    r = await send(client, 0.01)
    assert (r.status_code, r.json()["error"]) == (422, "LIMIT_DAILY")
    assert r.json()["details"] == {"amount": 0.01, "used_today": 10000.0, "limit": 10000.0}


async def test_cancelled_expired_and_older_transfers_dont_count(rich):
    client, pool = rich
    a = (await send(client, 5000)).json()["transfer_id"]
    await client.post(f"/transfers/{a}/cancel", json={"user_id": "demo_user"})
    b = (await send(client, 5000)).json()["transfer_id"]
    await pool.execute("UPDATE transactions SET otp_expires_at = now() - interval '1 second' WHERE id = $1", b)
    c = (await send(client, 5000)).json()["transfer_id"]
    await pool.execute("UPDATE transactions SET status = 'confirmed', created_at = $1 WHERE id = $2",
                       datetime.now(timezone.utc) - timedelta(days=1), c)
    assert (await send(client, 5000)).status_code == 200
    assert (await send(client, 5000)).status_code == 200  # $10,000 of live transfers today
    assert (await send(client, 1)).json()["error"] == "LIMIT_DAILY"


async def test_merchant_payments_dont_count(rich):
    client, pool = rich
    await pool.execute(
        """INSERT INTO transactions (id, from_account, to_account, amount, status, user_id, merchant_id, order_ref, channel)
           VALUES ('txn_m', $1, 'acc_merchant_fooddash_settlement', 9000, 'confirmed', 'demo_user', 'fooddash', 'o1', 'checkout')""",
        CHK)
    assert (await send(client, 5000)).status_code == 200
    assert (await send(client, 5000)).status_code == 200


async def test_idempotent_replay_isnt_counted_against_itself(rich):
    client, _ = rich
    assert (await send(client, 5000, key="k1")).status_code == 200
    assert (await send(client, 5000, key="k2")).status_code == 200
    replay = await send(client, 5000, key="k1")
    assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True
