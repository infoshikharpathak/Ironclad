from typing import Any


class BankError(Exception):
    """Rendered as {"error": code, "message": ..., "details": {...}} by the handler in main.py."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def account_not_found(account_id: str) -> BankError:
    return BankError(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")


def forbidden(message: str = "You do not have access to this resource") -> BankError:
    return BankError(403, "FORBIDDEN", message)


def transfer_not_found(transfer_id: str) -> BankError:
    return BankError(404, "TRANSFER_NOT_FOUND", f"Transfer {transfer_id} not found")


def invalid_transfer(message: str) -> BankError:
    return BankError(422, "INVALID_TRANSFER", message)
