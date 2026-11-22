"""Merchant payments API: a registered merchant asks a user to pay it.

The merchant is whoever owns the key the request is made with, and the payee
is that merchant's settlement account from the registry. Neither ever comes
from the request body. The payment is a pending transfer on the existing
OTP flow, so no money moves until the user types the OTP in Ironclad.

    POST /payments/requests              Authorization: Bearer mk_...
    GET  /payments/requests/{id}         (the merchant's own requests only)
    POST /payments/requests/{id}/cancel  (withdraw a pending request)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import config
from ..db import get_pool
from ..errors import BankError
from ..services import merchants as merchant_keys
from ..services import otp as otp_svc
from ..ws.notifications import manager

router = APIRouter(prefix="/payments", tags=["payments"])

# Anything that could name a payee. The payee is the merchant's settlement
# account from the registry, so a body that tries to set one is refused.
PAYEE_FIELDS = {"merchant_id", "merchant", "to_account", "payee", "payee_account", "settlement_account_id",
                "to", "recipient", "destination", "destination_account", "from_account"}

CHANNEL_INITIATOR = {"checkout": "merchant", "agent": "merchant_agent"}


class PaymentRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_ref: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    user_id: str = Field(min_length=1, max_length=100)
    channel: Literal["checkout", "agent"]
    idempotency_key: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=200)


class PaymentRequestOut(BaseModel):
    """Never contains the OTP: the merchant (or its AI agent) is not the payer."""

    payment_request_id: str
    status: Literal["pending_otp", "confirmed", "cancelled", "expired"]
    amount: float
    merchant_display_name: str
    order_ref: str
    channel: str
    expires_at: datetime | None
    created_at: datetime | None = None
    confirmed_at: datetime | None = None
    idempotent_replay: bool = False


async def _merchant(authorization: str | None):
    key = merchant_keys.bearer_key(authorization)
    if key is None:
        raise BankError(401, "MERCHANT_KEY_REQUIRED", "Send the merchant key as 'Authorization: Bearer mk_...'.")
    merchant = await merchant_keys.merchant_for_key(get_pool(), key)
    if merchant is None:
        raise BankError(401, "MERCHANT_KEY_INVALID", "Unknown merchant key.")
    return merchant


def _request_hash(body: PaymentRequestIn) -> str:
    canonical = {
        "order_ref": body.order_ref, "amount": str(body.amount.quantize(Decimal("0.01"))), "user_id": body.user_id,
        "channel": body.channel, "description": body.description,
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def _status(row) -> str:
    if row["status"] == "confirmed":
        return "confirmed"
    if row["status"] == "pending_otp":
        expired = row["otp_expires_at"] and datetime.now(timezone.utc) > row["otp_expires_at"]
        return "expired" if expired else "pending_otp"
    if row["closed_reason"] == "expired":
        return "expired"
    # declined, merchant_cancelled, too many OTP attempts, or failed at confirm (insufficient funds)
    return "cancelled"


def _out(row, merchant, *, replay: bool = False) -> PaymentRequestOut:
    return PaymentRequestOut(
        payment_request_id=row["id"], status=_status(row), amount=float(row["amount"]),
        merchant_display_name=merchant["display_name"], order_ref=row["order_ref"], channel=row["channel"],
        expires_at=row["otp_expires_at"], created_at=row["created_at"], confirmed_at=row["confirmed_at"],
        idempotent_replay=replay,
    )


async def _expire_if_due(row):
    """A pending request past its OTP expiry is closed as expired (the user is told)."""
    if row["status"] != "pending_otp" or _status(row) != "expired":
        return row
    pool = get_pool()
    updated = await pool.fetchrow(
        "UPDATE transactions SET status = 'cancelled', closed_reason = 'expired' "
        "WHERE id = $1 AND status = 'pending_otp' RETURNING *",
        row["id"],
    )
    if updated is None:  # someone else closed it first
        return await pool.fetchrow("SELECT * FROM transactions WHERE id = $1", row["id"])
    await manager.send_to_user(
        row["user_id"], {"type": "transfer_cancelled", "data": {"transfer_id": row["id"], "reason": "OTP expired"}}
    )
    return updated


@router.post("/requests", response_model=PaymentRequestOut)
async def create_payment_request(request: Request, authorization: str | None = Header(default=None)):
    # Checks run in this order: key, merchant status, body, channel, amount,
    # idempotency, balance. The body is parsed by hand so a bad key is a 401
    # even when the body is also wrong.
    merchant = await _merchant(authorization)
    if merchant["status"] != "active":
        raise BankError(403, "MERCHANT_SUSPENDED", f"Merchant {merchant['merchant_id']} is {merchant['status']}.")

    try:
        raw = await request.json()
    except ValueError:
        raise BankError(422, "INVALID_PAYMENT_REQUEST", "Body must be a JSON object.")
    if not isinstance(raw, dict):
        raise BankError(422, "INVALID_PAYMENT_REQUEST", "Body must be a JSON object.")
    payee = sorted(PAYEE_FIELDS & raw.keys())
    if payee:
        raise BankError(422, "PAYEE_NOT_ALLOWED",
                        "The payee is the merchant's registered settlement account and the payer is the user's "
                        "checking account; neither can be set in the request.",
                        {"fields": payee})
    try:
        body = PaymentRequestIn.model_validate(raw)
    except ValidationError as exc:
        raise BankError(422, "INVALID_PAYMENT_REQUEST", "Invalid payment request.",
                        {"errors": json.loads(exc.json(include_url=False, include_context=False))})

    if body.channel == "agent" and not merchant["agent_payments_allowed"]:
        raise BankError(403, "AGENT_PAYMENTS_NOT_ALLOWED",
                        f"{merchant['display_name']} is not allowed to request payments from an AI agent.")
    if body.amount <= 0:
        raise BankError(422, "INVALID_AMOUNT", "Amount must be positive.")
    if body.amount > merchant["max_payment_amount"]:
        raise BankError(422, "AMOUNT_OVER_LIMIT",
                        f"Amount ${body.amount} is over {merchant['display_name']}'s limit of "
                        f"${merchant['max_payment_amount']}.",
                        {"amount": float(body.amount), "limit": float(merchant["max_payment_amount"])})

    pool = get_pool()
    request_hash = _request_hash(body)
    # Scoped per merchant, so two merchants can't collide (or probe each other's keys).
    idem_key = f"merchant:{merchant['merchant_id']}:{body.idempotency_key}"
    existing = await pool.fetchrow("SELECT * FROM transactions WHERE idempotency_key = $1", idem_key)
    if existing is not None:
        if existing["request_hash"] != request_hash:
            raise BankError(409, "IDEMPOTENCY_KEY_REUSED",
                            "This idempotency key was already used with a different request.",
                            {"payment_request_id": existing["id"]})
        return _out(await _expire_if_due(existing), merchant, replay=True)

    payer = await pool.fetchrow(
        "SELECT * FROM accounts WHERE user_id = $1 AND account_type = 'checking' ORDER BY created_at, id LIMIT 1",
        body.user_id,
    )
    if payer is None:
        raise BankError(404, "PAYER_NOT_FOUND", f"No checking account for user {body.user_id}.")
    payee_row = await pool.fetchrow("SELECT * FROM accounts WHERE id = $1", merchant["settlement_account_id"])
    if payee_row is None:  # registry misconfiguration, not the caller's fault
        raise BankError(500, "SETTLEMENT_ACCOUNT_MISSING", "The merchant's settlement account doesn't exist.")
    if payer["balance"] < body.amount:
        raise BankError(422, "INSUFFICIENT_FUNDS",
                        f"{payer['name']} balance (${payer['balance']}) is less than the payment (${body.amount}).",
                        {"balance": float(payer["balance"]), "amount": float(body.amount)})

    otp_code = otp_svc.generate_otp()
    otp_hash = await asyncio.to_thread(otp_svc.hash_otp, otp_code)
    payment_id = "txn_" + uuid.uuid4().hex[:12]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.OTP_TTL_SECONDS)
    description = body.description or f"{merchant['display_name']} order {body.order_ref}"
    initiated_by = CHANNEL_INITIATOR[body.channel]

    row = await pool.fetchrow(
        """
        INSERT INTO transactions (id, from_account, to_account, amount, status, description, otp_hash,
                                  otp_expires_at, idempotency_key, initiated_by, user_id,
                                  merchant_id, order_ref, channel, request_hash)
        VALUES ($1, $2, $3, $4, 'pending_otp', $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING *
        """,
        payment_id, payer["id"], payee_row["id"], body.amount, description, otp_hash, expires_at, idem_key,
        initiated_by, body.user_id, merchant["merchant_id"], body.order_ref, body.channel, request_hash,
    )
    if row is None:  # a concurrent request with the same key won the insert
        existing = await pool.fetchrow("SELECT * FROM transactions WHERE idempotency_key = $1", idem_key)
        if existing["request_hash"] != request_hash:
            raise BankError(409, "IDEMPOTENCY_KEY_REUSED",
                            "This idempotency key was already used with a different request.",
                            {"payment_request_id": existing["id"]})
        return _out(existing, merchant, replay=True)

    # The OTP goes only to the user's dashboard (WebSocket push, or
    # GET /transfers/pending), never back to the merchant.
    await manager.send_to_user(body.user_id, {
        "type": "otp_required",
        "data": {
            "transfer_id": payment_id,
            "amount": float(body.amount),
            "from_account": payer["id"],
            "to_account": payee_row["id"],
            "from_name": payer["name"],
            "to_name": merchant["display_name"],
            "description": description,
            "initiated_by": initiated_by,
            "merchant_id": merchant["merchant_id"],
            "merchant_display_name": merchant["display_name"],
            "order_ref": body.order_ref,
            "channel": body.channel,
            "otp_code": otp_code,
        },
    })
    return _out(row, merchant)


@router.get("/requests/{payment_request_id}", response_model=PaymentRequestOut)
async def get_payment_request(payment_request_id: str, authorization: str | None = Header(default=None)):
    merchant = await _merchant(authorization)
    row = await get_pool().fetchrow(
        "SELECT * FROM transactions WHERE id = $1 AND merchant_id = $2", payment_request_id, merchant["merchant_id"]
    )
    if row is None:  # another merchant's request looks exactly like a missing one
        raise BankError(404, "PAYMENT_REQUEST_NOT_FOUND", f"Payment request {payment_request_id} not found.")
    return _out(await _expire_if_due(row), merchant)


@router.post("/requests/{payment_request_id}/cancel", response_model=PaymentRequestOut)
async def cancel_payment_request(payment_request_id: str, authorization: str | None = Header(default=None)):
    """The merchant withdraws its own pending request (e.g. the order was
    cancelled). Idempotent: an already cancelled or expired request is
    returned as it is. A confirmed one can't be cancelled (409): the money
    has moved."""
    merchant = await _merchant(authorization)
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM transactions WHERE id = $1 AND merchant_id = $2", payment_request_id, merchant["merchant_id"]
    )
    if row is None:
        raise BankError(404, "PAYMENT_REQUEST_NOT_FOUND", f"Payment request {payment_request_id} not found.")
    row = await _expire_if_due(row)
    if row["status"] == "confirmed":
        raise BankError(409, "PAYMENT_ALREADY_CONFIRMED",
                        "This payment was already confirmed by the user; it can't be cancelled.",
                        {"payment_request_id": payment_request_id})
    if row["status"] != "pending_otp":
        return _out(row, merchant)  # already cancelled, expired or failed: nothing to do

    updated = await pool.fetchrow(
        "UPDATE transactions SET status = 'cancelled', closed_reason = 'merchant_cancelled', otp_hash = NULL "
        "WHERE id = $1 AND status = 'pending_otp' RETURNING *",
        payment_request_id,
    )
    if updated is None:  # the user confirmed or declined it in the meantime
        current = await pool.fetchrow("SELECT * FROM transactions WHERE id = $1", payment_request_id)
        if current["status"] == "confirmed":
            raise BankError(409, "PAYMENT_ALREADY_CONFIRMED",
                            "This payment was already confirmed by the user; it can't be cancelled.",
                            {"payment_request_id": payment_request_id})
        return _out(current, merchant)
    await manager.send_to_user(row["user_id"], {
        "type": "transfer_cancelled",
        "data": {"transfer_id": payment_request_id, "reason": f"Cancelled by {merchant['display_name']}"},
    })
    return _out(updated, merchant)
