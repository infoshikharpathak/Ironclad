"""The OTP must reach only the person, never the /initiate caller (which may
be an AI agent). Runs the real FastAPI app with a fake DB pool."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import app.main as bank
from app.routes import transfers


class FakePool:
    def __init__(self):
        self.accounts = {
            "acc_demo_checking": {"id": "acc_demo_checking", "user_id": "demo_user", "name": "Checking",
                                  "balance": Decimal("500"), "owner_name": None},
            "ACC-10043-CHK": {"id": "ACC-10043-CHK", "user_id": "bob", "name": "Checking",
                              "balance": Decimal("10"), "owner_name": "Bob Smith"},
        }
        self.transactions = {}

    async def fetchrow(self, sql, *args):
        if "FROM accounts" in sql:
            return self.accounts.get(args[0])
        if "idempotency_key" in sql:
            return next((t for t in self.transactions.values() if t["idempotency_key"] == args[0]), None)
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        assert sql.strip().startswith("INSERT INTO transactions")
        tid, frm, to, amount, desc, otp_hash, expires, idem, by, user = args
        self.transactions[tid] = {
            "id": tid, "from_account": frm, "to_account": to, "amount": amount, "status": "pending_otp",
            "otp_hash": otp_hash, "otp_expires_at": expires, "idempotency_key": idem,
        }


@pytest.fixture
def client(monkeypatch):
    pool, pushed = FakePool(), []

    async def push(user_id, message):
        pushed.append((user_id, message))

    monkeypatch.setattr(transfers, "get_pool", lambda: pool)
    monkeypatch.setattr(transfers.manager, "send_to_user", push)
    bank.app.router.lifespan_context = None  # no real DB pool at startup
    return TestClient(bank.app), pool, pushed


BODY = {"user_id": "demo_user", "from_account": "acc_demo_checking", "to_account": "ACC-10043-CHK",
        "amount": 25, "description": "dinner", "initiated_by": "agent", "idempotency_key": "agent_abc"}


def test_initiate_response_never_contains_the_otp(client):
    c, pool, pushed = client
    resp = c.post("/transfers/initiate", json=BODY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending_otp"
    assert "otp_code" not in body

    # ...but the person gets it on the dashboard, and it is the real code
    ((user, message),) = pushed
    code = message["data"]["otp_code"]
    assert user == "demo_user" and message["type"] == "otp_required" and code
    assert code not in resp.text  # the code appears nowhere in what the caller received
    from app.services import otp as otp_svc
    (txn,) = pool.transactions.values()
    assert otp_svc.verify_otp(code, txn["otp_hash"])


def test_idempotent_replay_never_contains_the_otp(client):
    c, _, pushed = client
    c.post("/transfers/initiate", json=BODY)
    replay = c.post("/transfers/initiate", json=BODY)
    assert replay.json()["idempotent_replay"] is True and "otp_code" not in replay.json()
    assert len(pushed) == 1  # no second code issued
