from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------- Requests ----------


class TransferInitiateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    from_account: str = Field(min_length=1)
    to_account: str = Field(min_length=1)
    # Range and precision are checked in the route so they surface as INVALID_TRANSFER.
    amount: Decimal
    description: str = Field(default="", max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    initiated_by: str = Field(default="user", min_length=1, max_length=64)


class TransferConfirmRequest(BaseModel):
    user_id: str = Field(min_length=1)
    otp_code: str = Field(min_length=1, max_length=16)


class ResetRequest(BaseModel):
    user_id: str = Field(min_length=1)


class DepositRequest(BaseModel):
    user_id: str = Field(min_length=1)
    amount: Decimal


# ---------- Responses ----------


class Account(BaseModel):
    id: str
    name: str
    account_type: str
    balance: float
    currency: str


class AccountsResponse(BaseModel):
    accounts: list[Account]


class Transaction(BaseModel):
    id: str
    from_account: str
    to_account: str
    amount: float
    status: str
    description: str
    initiated_by: str
    otp_attempts: int
    otp_expires_at: datetime | None
    created_at: datetime
    confirmed_at: datetime | None


class TransactionsResponse(BaseModel):
    transactions: list[Transaction]
    limit: int
    offset: int


class TransferInitiateResponse(BaseModel):
    transfer_id: str
    status: str
    message: str
    amount: float
    from_account: str
    to_account: str
    # Demo only: the plaintext OTP. None when an idempotent replay returns an existing
    # transfer, because only the bcrypt hash is stored.
    otp_code: str | None
    expires_at: datetime | None
    idempotent_replay: bool = False


class TransferConfirmResponse(BaseModel):
    transfer_id: str
    status: str
    message: str
    transaction: Transaction
    new_balances: dict[str, float]


class ResetResponse(BaseModel):
    status: str
    accounts: list[Account]


# --- Directory / Lookup (public) ---


class PublicAccount(BaseModel):
    """What anyone can see about an account — no balance exposed."""
    account_number: str
    owner_name: str
    account_type: str
    currency: str


class DirectoryResponse(BaseModel):
    accounts: list[PublicAccount]


def public_account_from_row(row) -> PublicAccount:
    return PublicAccount(
        account_number=row["id"],
        owner_name=row["owner_name"] or row["name"],
        account_type=row["account_type"],
        currency=row["currency"],
    )


def account_from_row(row) -> Account:
    return Account(
        id=row["id"],
        name=row["name"],
        account_type=row["account_type"],
        balance=float(row["balance"]),
        currency=row["currency"],
    )


def transaction_from_row(row) -> Transaction:
    return Transaction(
        id=row["id"],
        from_account=row["from_account"],
        to_account=row["to_account"],
        amount=float(row["amount"]),
        status=row["status"],
        description=row["description"] or "",
        initiated_by=row["initiated_by"],
        otp_attempts=row["otp_attempts"] or 0,
        otp_expires_at=row["otp_expires_at"],
        created_at=row["created_at"],
        confirmed_at=row["confirmed_at"],
    )
