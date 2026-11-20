from fastapi import APIRouter, Query

from ..db import get_pool
from ..errors import BankError, account_not_found, forbidden
from ..models import (
    Account,
    AccountsResponse,
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
    rows = await get_pool().fetch(
        """
        SELECT *
        FROM transactions
        WHERE (from_account = $1 OR to_account = $1)
          AND user_id = $2
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


@router.post("/reset", response_model=ResetResponse)
async def reset_accounts(user_id: str = Query(min_length=1)):
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
