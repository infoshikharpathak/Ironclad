import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..db import get_pool
from ..errors import BankError, account_not_found, forbidden, transfer_not_found, invalid_transfer
from ..models import (
    TransferInitiateRequest,
    TransferConfirmRequest,
    TransferInitiateResponse,
    TransferConfirmResponse,
    Transaction,
    account_from_row,
    transaction_from_row,
)
from ..services import otp as otp_svc
from ..services.ledger import InsufficientFunds, execute_transfer
from ..ws.notifications import manager
from .. import config

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.get("/pending")
async def list_pending_transfers(user_id: str = Query(min_length=1)):
    """Return all pending_otp transfers for the user, with fresh OTP codes."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT t.*, a_from.name AS from_name,
               COALESCE(a_to.owner_name, a_to.name) AS to_name
        FROM transactions t
        JOIN accounts a_from ON a_from.id = t.from_account
        JOIN accounts a_to   ON a_to.id   = t.to_account
        WHERE t.user_id = $1 AND t.status = 'pending_otp'
        ORDER BY t.created_at DESC
        """,
        user_id,
    )

    pending = []
    now = datetime.now(timezone.utc)
    for row in rows:
        if row["otp_expires_at"] and now > row["otp_expires_at"]:
            await pool.execute(
                "UPDATE transactions SET status = 'cancelled' WHERE id = $1", row["id"]
            )
            continue

        otp_code = otp_svc.generate_otp()
        otp_hash = await asyncio.to_thread(otp_svc.hash_otp, otp_code)
        await pool.execute(
            "UPDATE transactions SET otp_hash = $1, otp_attempts = 0 WHERE id = $2",
            otp_hash, row["id"],
        )

        pending.append({
            "transfer_id": row["id"],
            "amount": float(row["amount"]),
            "from_account": row["from_account"],
            "to_account": row["to_account"],
            "from_name": row["from_name"],
            "to_name": row["to_name"],
            "description": row["description"] or "",
            "initiated_by": row["initiated_by"],
            "otp_code": otp_code,
            "expires_at": row["otp_expires_at"].isoformat() if row["otp_expires_at"] else None,
            "created_at": row["created_at"].isoformat(),
        })

    return {"transfers": pending}


@router.post("/initiate", response_model=TransferInitiateResponse)
async def initiate_transfer(body: TransferInitiateRequest):
    pool = get_pool()

    # --- validation ---
    if body.from_account == body.to_account:
        raise invalid_transfer("Source and destination accounts must be different")
    if body.amount <= 0:
        raise invalid_transfer("Transfer amount must be positive")

    # Ownership check
    from_row = await pool.fetchrow("SELECT * FROM accounts WHERE id = $1", body.from_account)
    if from_row is None:
        raise account_not_found(body.from_account)
    if from_row["user_id"] != body.user_id:
        raise forbidden("You do not own the source account")

    to_row = await pool.fetchrow("SELECT * FROM accounts WHERE id = $1", body.to_account)
    if to_row is None:
        raise account_not_found(body.to_account)

    # Sufficient balance (advisory — the real guard is the CHECK constraint + ledger lock)
    if from_row["balance"] < body.amount:
        raise BankError(
            422,
            "INSUFFICIENT_FUNDS",
            f"{from_row['name']} balance (${from_row['balance']}) is less than transfer amount (${body.amount})",
            {"balance": float(from_row["balance"]), "amount": float(body.amount)},
        )

    # --- idempotency ---
    if body.idempotency_key:
        existing = await pool.fetchrow(
            "SELECT * FROM transactions WHERE idempotency_key = $1", body.idempotency_key
        )
        if existing is not None:
            return TransferInitiateResponse(
                transfer_id=existing["id"],
                status=existing["status"],
                message="Idempotent replay of existing transfer",
                amount=float(existing["amount"]),
                from_account=existing["from_account"],
                to_account=existing["to_account"],
                expires_at=existing["otp_expires_at"],
                idempotent_replay=True,
            )

    # --- generate OTP ---
    otp_code = otp_svc.generate_otp()
    otp_hash = await asyncio.to_thread(otp_svc.hash_otp, otp_code)

    transfer_id = "txn_" + uuid.uuid4().hex[:12]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.OTP_TTL_SECONDS)

    await pool.execute(
        """
        INSERT INTO transactions (id, from_account, to_account, amount, status, description,
                                  otp_hash, otp_expires_at, idempotency_key, initiated_by, user_id)
        VALUES ($1, $2, $3, $4, 'pending_otp', $5, $6, $7, $8, $9, $10)
        """,
        transfer_id,
        body.from_account,
        body.to_account,
        body.amount,
        body.description,
        otp_hash,
        expires_at,
        body.idempotency_key,
        body.initiated_by,
        body.user_id,
    )

    # Push OTP via WebSocket so any connected browser shows the modal.
    # Include full transfer details so the user can review before entering OTP.
    # This (and GET /transfers/pending) is the ONLY way the code leaves the
    # bank: the /initiate response below never contains it, because the
    # caller may be an AI agent.
    to_owner = to_row.get("owner_name") or to_row["name"]
    await manager.send_to_user(
        body.user_id,
        {
            "type": "otp_required",
            "data": {
                "transfer_id": transfer_id,
                "amount": float(body.amount),
                "from_account": body.from_account,
                "to_account": body.to_account,
                "from_name": from_row["name"],
                "to_name": to_owner,
                "description": body.description,
                "initiated_by": body.initiated_by,
                "otp_code": otp_code,
            },
        },
    )

    return TransferInitiateResponse(
        transfer_id=transfer_id,
        status="pending_otp",
        message="OTP sent to your bank dashboard. Please confirm.",
        amount=float(body.amount),
        from_account=body.from_account,
        to_account=body.to_account,
        expires_at=expires_at,
    )


@router.post("/{transfer_id}/confirm", response_model=TransferConfirmResponse)
async def confirm_transfer(transfer_id: str, body: TransferConfirmRequest):
    pool = get_pool()

    async with pool.acquire() as conn:
        # Lock the transaction row for the duration of this connection.
        txn = await conn.fetchrow(
            "SELECT * FROM transactions WHERE id = $1 FOR UPDATE", transfer_id
        )
        if txn is None:
            raise transfer_not_found(transfer_id)
        if txn["user_id"] != body.user_id:
            raise forbidden("You do not own this transfer")
        if txn["status"] != "pending_otp":
            raise BankError(422, "TRANSFER_NOT_PENDING", f"Transfer is {txn['status']}, not pending_otp")

        # Expiry
        if txn["otp_expires_at"] and datetime.now(timezone.utc) > txn["otp_expires_at"]:
            await conn.execute(
                "UPDATE transactions SET status = 'cancelled' WHERE id = $1", transfer_id
            )
            await manager.send_to_user(
                body.user_id,
                {"type": "transfer_cancelled", "data": {"transfer_id": transfer_id, "reason": "OTP expired"}},
            )
            raise BankError(422, "OTP_EXPIRED", "OTP has expired. Please initiate a new transfer.")

        # Attempts guard
        attempts = (txn["otp_attempts"] or 0) + 1
        await conn.execute(
            "UPDATE transactions SET otp_attempts = $1 WHERE id = $2", attempts, transfer_id
        )

        # Verify OTP
        valid = await asyncio.to_thread(otp_svc.verify_otp, body.otp_code, txn["otp_hash"])
        if not valid:
            if attempts >= config.OTP_MAX_ATTEMPTS:
                await conn.execute(
                    "UPDATE transactions SET status = 'cancelled' WHERE id = $1", transfer_id
                )
                await manager.send_to_user(
                    body.user_id,
                    {"type": "transfer_cancelled", "data": {"transfer_id": transfer_id, "reason": "Too many OTP attempts"}},
                )
                raise BankError(
                    422,
                    "OTP_MAX_ATTEMPTS",
                    "Too many incorrect OTP attempts. Transfer cancelled.",
                    {"attempts": attempts},
                )
            remaining = config.OTP_MAX_ATTEMPTS - attempts
            raise BankError(
                422,
                "OTP_INVALID",
                f"Incorrect OTP. {remaining} attempt(s) remaining.",
                {"attempts": attempts, "remaining": remaining},
            )

        # --- Execute the transfer atomically ---
        try:
            await execute_transfer(
                conn,
                txn["from_account"],
                txn["to_account"],
                txn["amount"],
                transfer_id,
            )
        except InsufficientFunds as exc:
            await conn.execute(
                "UPDATE transactions SET status = 'failed' WHERE id = $1", transfer_id
            )
            raise BankError(
                422,
                "INSUFFICIENT_FUNDS",
                str(exc),
                {"balance": float(exc.balance), "amount": float(exc.amount)},
            )

        # Fetch updated state
        updated_txn = await conn.fetchrow("SELECT * FROM transactions WHERE id = $1", transfer_id)
        from_bal = await conn.fetchval(
            "SELECT balance FROM accounts WHERE id = $1", txn["from_account"]
        )
        to_bal = await conn.fetchval(
            "SELECT balance FROM accounts WHERE id = $1", txn["to_account"]
        )

    new_balances = {txn["from_account"]: float(from_bal), txn["to_account"]: float(to_bal)}

    # Push confirmation via WebSocket
    await manager.send_to_user(
        body.user_id,
        {
            "type": "transfer_confirmed",
            "data": {
                "transfer_id": transfer_id,
                "from_account": txn["from_account"],
                "to_account": txn["to_account"],
                "new_balances": new_balances,
            },
        },
    )

    return TransferConfirmResponse(
        transfer_id=transfer_id,
        status="confirmed",
        message="Transfer confirmed successfully",
        transaction=transaction_from_row(updated_txn),
        new_balances=new_balances,
    )


class CancelRequest(BaseModel):
    user_id: str


@router.post("/{transfer_id}/cancel")
async def cancel_transfer(transfer_id: str, body: CancelRequest):
    """Cancel a pending transfer (user declined)."""
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM transactions WHERE id = $1", transfer_id)
    if row is None:
        raise transfer_not_found(transfer_id)
    if row["user_id"] != body.user_id:
        raise forbidden("You do not own this transfer")
    if row["status"] != "pending_otp":
        raise BankError(422, "TRANSFER_NOT_PENDING", f"Transfer is {row['status']}, not pending_otp")

    await pool.execute(
        "UPDATE transactions SET status = 'cancelled' WHERE id = $1", transfer_id
    )
    await manager.send_to_user(
        body.user_id,
        {"type": "transfer_cancelled", "data": {"transfer_id": transfer_id, "reason": "Declined by user"}},
    )
    return {"transfer_id": transfer_id, "status": "cancelled", "message": "Transfer cancelled."}


@router.get("/{transfer_id}/status")
async def transfer_status(transfer_id: str, user_id: str = Query(min_length=1)):
    row = await get_pool().fetchrow("SELECT * FROM transactions WHERE id = $1", transfer_id)
    if row is None:
        raise transfer_not_found(transfer_id)
    if row["user_id"] != user_id:
        raise forbidden("You do not own this transfer")
    return {"transfer": transaction_from_row(row)}
