from fastapi import APIRouter, Query

from ..db import get_pool
from ..errors import BankError, account_not_found, forbidden
from ..models import (
    Account,
    AccountsResponse,
    DepositRequest,
    ResetRequest,
    ResetResponse,
    TransactionsResponse,
    account_from_row,
    transaction_from_row,
)
from .. import config

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _ensure_ownership(account_id: str, user_id: str) -> dict:
    """Return the account row or raise ACCOUNT_NOT_FOUND / FORBIDDEN."""
    row = await get_pool().fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
    if row is None:
        raise account_not_found(account_id)
    if row["user_id"] != user_id:
        raise forbidden("You do not own this account")
    return row


@router.get("", response_model=AccountsResponse)
async def list_accounts(user_id: str = Query(min_length=1)):
    rows = await get_pool().fetch(
        "SELECT * FROM accounts WHERE user_id = $1 ORDER BY account_type", user_id
    )
    return AccountsResponse(accounts=[account_from_row(r) for r in rows])


@router.get("/{account_id}", response_model=Account)
async def get_account(account_id: str, user_id: str = Query(min_length=1)):
    row = await _ensure_ownership(account_id, user_id)
    return account_from_row(row)


@router.get("/{account_id}/transactions", response_model=TransactionsResponse)
async def list_transactions(
    account_id: str,
    user_id: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    await _ensure_ownership(account_id, user_id)
    # The user's own transfers in or out of this account, plus money other
    # people sent to it once it went through. (Someone else's pending or
    # cancelled transfer is theirs, not this user's.)
    rows = await get_pool().fetch(
        """
        SELECT *
        FROM transactions
        WHERE (from_account = $1 AND user_id = $2)
           OR (to_account = $1 AND (user_id = $2 OR status = 'confirmed'))
        ORDER BY created_at DESC
        LIMIT $3 OFFSET $4
        """,
        account_id,
        user_id,
        limit,
        offset,
    )
    return TransactionsResponse(
        transactions=[transaction_from_row(r) for r in rows],
        limit=limit,
        offset=offset,
    )


@router.post("/{account_id}/deposit", response_model=Account)
async def deposit(account_id: str, body: DepositRequest):
    """Add funds to an account the user owns. No OTP — this is a demo convenience
    so users can top up their accounts without an external funding source."""
    if body.amount <= 0:
        raise BankError(422, "INVALID_TRANSFER", "Deposit amount must be positive")

    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
    if row is None:
        raise account_not_found(account_id)
    if row["user_id"] != body.user_id:
        raise forbidden("You do not own this account")

    await pool.execute(
        "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
        body.amount,
        account_id,
    )
    updated = await pool.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
    return account_from_row(updated)


@router.post("/reset", response_model=ResetResponse)
async def reset_accounts(body: ResetRequest | None = None, user_id: str | None = Query(default=None, min_length=1)):
    # Accept user_id from JSON body (agent calls) or query param (browser calls)
    user_id = (body.user_id if body else None) or user_id
    if not user_id:
        raise BankError(422, "INVALID_TRANSFER", "user_id is required")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM transactions WHERE user_id = $1", user_id)
            await conn.execute(
                "UPDATE accounts SET balance = $1 WHERE user_id = $2 AND account_type = 'checking'",
                config.SEED_BALANCES["checking"],
                user_id,
            )
            await conn.execute(
                "UPDATE accounts SET balance = $1 WHERE user_id = $2 AND account_type = 'savings'",
                config.SEED_BALANCES["savings"],
                user_id,
            )
    rows = await pool.fetch(
        "SELECT * FROM accounts WHERE user_id = $1 ORDER BY account_type", user_id
    )
    return ResetResponse(status="ok", accounts=[account_from_row(r) for r in rows])
