"""Structured logs: LogScribe's JSON format, incidents at ERROR, and no
secrets or sensitive data in the log file (OTPs, keys, account numbers,
request content)."""

from __future__ import annotations

import json
import logging
import sys

import pytest

from app import logs
from app.services import merchants

pytestmark = pytest.mark.anyio

CHK, BOB = "acc_demo_user_checking", "ACC-10043-CHK"
WRONG_OTP = "975310"
UNKNOWN_ACCOUNT = "ACC-77123456-CHK"
POLICY_KEY = "pk_live_supersecretpolicykey123"
SEARCH_WORDS = "my secret question about wire fees"


@pytest.fixture
def log_file(tmp_path):
    logs.configure("bank-service", tmp_path)
    yield tmp_path / "bank-service.log"
    logs.configure("bank-service")  # back to the session's log dir


def read(path) -> list[dict]:
    for h in logging.getLogger(logs.LOGGER_NAME).handlers:
        h.flush()
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def test_lines_are_logscribe_json_with_request_ids(bank, log_file):
    client, _, _ = bank
    r = await client.get("/health", headers={"X-Request-ID": "req-abc-123"})
    assert r.headers["X-Request-ID"] == "req-abc-123"
    line = read(log_file)[-1]
    assert {"timestamp", "service_name", "level", "message", "request_id", "endpoint",
            "duration_ms"} <= set(line)
    assert (line["service_name"], line["level"], line["request_id"], line["endpoint"]) == (
        "bank-service", "INFO", "req-abc-123", "/health")
    # A malformed incoming ID is replaced, not logged.
    r = await client.get("/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert r.headers["X-Request-ID"] != "bad id\nwith newline"


async def test_otp_max_attempts_and_limits_are_incidents(bank, log_file):
    client, pool, _ = bank
    await pool.execute("UPDATE accounts SET balance = 50000 WHERE id = $1", CHK)
    tid = (await client.post("/transfers/initiate", json={
        "user_id": "demo_user", "from_account": CHK, "to_account": BOB, "amount": 25})).json()["transfer_id"]
    for _ in range(3):
        await client.post(f"/transfers/{tid}/confirm", json={"user_id": "demo_user", "otp_code": WRONG_OTP})
    r = await client.post("/transfers/initiate", json={
        "user_id": "demo_user", "from_account": CHK, "to_account": BOB, "amount": 5000.01})
    assert r.json()["error"] == "LIMIT_PER_TRANSFER"
    lines = read(log_file)
    by_type = {line.get("error_type"): line for line in lines if line.get("error_type")}
    assert by_type["OTP_INVALID"]["level"] == "WARNING"
    assert by_type["OTP_MAX_ATTEMPTS"]["level"] == "ERROR"
    assert by_type["OTP_MAX_ATTEMPTS"]["endpoint"] == "/transfers/{transfer_id}/confirm"
    assert by_type["OTP_MAX_ATTEMPTS"]["attempts"] == 3
    assert by_type["LIMIT_PER_TRANSFER"]["level"] == "ERROR"


async def test_no_secrets_or_sensitive_data_in_the_log(bank, log_file):
    """Requests carrying an OTP, merchant and policy keys, an account number
    and user words: none of them may appear in the log file."""
    client, pool, _ = bank
    merchant_key = merchants.new_key()  # never registered: the merchant API rejects it
    tid = (await client.post("/transfers/initiate", json={
        "user_id": "demo_user", "from_account": CHK, "to_account": BOB, "amount": 10})).json()["transfer_id"]
    for _ in range(3):
        await client.post(f"/transfers/{tid}/confirm", json={"user_id": "demo_user", "otp_code": WRONG_OTP})
    r = await client.post("/payments/requests", headers={"Authorization": f"Bearer {merchant_key}"},
                          json={"order_ref": "o", "amount": 1, "user_id": "demo_user", "channel": "checkout",
                                "idempotency_key": "k"})
    assert r.json()["error"] == "MERCHANT_KEY_INVALID"
    r = await client.get("/policies/search", params={"q": SEARCH_WORDS},
                         headers={"Authorization": f"Bearer {POLICY_KEY}"})
    assert r.json()["error"] == "POLICY_KEY_INVALID"
    r = await client.get(f"/directory/lookup/{UNKNOWN_ACCOUNT}")
    assert r.json()["error"] == "ACCOUNT_NOT_FOUND"

    text = log_file.read_text()
    lines = read(log_file)
    for secret in (WRONG_OTP, merchant_key, merchant_key[3:], POLICY_KEY, UNKNOWN_ACCOUNT, "77123456",
                   SEARCH_WORDS, "wire fees", "devpassword"):
        assert secret not in text, f"{secret!r} is in the log"
    errors = {line["error_type"]: line for line in lines if line.get("error_type")}
    assert errors["MERCHANT_KEY_INVALID"]["level"] == "ERROR"
    assert errors["POLICY_KEY_INVALID"]["level"] == "ERROR"
    assert "****3456" in errors["ACCOUNT_NOT_FOUND"]["message"]  # masked to the last 4


def test_exceptions_are_scrubbed_in_message_and_stack_trace(tmp_path):
    logger = logs.configure("bank-service", tmp_path)
    try:
        try:
            raise RuntimeError(f"failed for {UNKNOWN_ACCOUNT} with otp_code={WRONG_OTP} "
                               f"Authorization: Bearer {POLICY_KEY} postgresql://anvil:devpassword@db/x")
        except RuntimeError as exc:
            message, extra = logs.describe_exception(exc)
            logger.error(message, exc_info=sys.exc_info(), extra=extra)
        line = read(tmp_path / "bank-service.log")[-1]
    finally:
        logs.configure("bank-service")
    assert line["error_type"] == "RuntimeError" and "Traceback" in line["stack_trace"]
    blob = json.dumps(line)
    for secret in (UNKNOWN_ACCOUNT, WRONG_OTP, POLICY_KEY, "devpassword"):
        assert secret not in blob


def test_database_errors_are_named():
    message, _ = logs.describe_exception(ConnectionRefusedError(61, "Connect call failed ('127.0.0.1', 5432)"))
    assert message.startswith("Database error: ConnectionRefusedError")
