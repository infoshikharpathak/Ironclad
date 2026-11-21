from fastapi import APIRouter

from ..db import get_pool
from ..errors import account_not_found
from ..models import DirectoryResponse, PublicAccount, public_account_from_row

router = APIRouter(prefix="/directory", tags=["directory"])


@router.get("", response_model=DirectoryResponse)
async def list_public_accounts():
    """List all publicly discoverable accounts (the demo people you can send money to)."""
    rows = await get_pool().fetch(
        "SELECT * FROM accounts WHERE is_public = true ORDER BY owner_name"
    )
    return DirectoryResponse(accounts=[public_account_from_row(r) for r in rows])


@router.get("/lookup/{account_number}", response_model=PublicAccount)
async def lookup_account(account_number: str):
    """Look up any account by its number.  Returns public info only (no balance)."""
    row = await get_pool().fetchrow("SELECT * FROM accounts WHERE id = $1", account_number)
    if row is None:
        raise account_not_found(account_number)
    return public_account_from_row(row)
