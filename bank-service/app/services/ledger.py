from decimal import Decimal

import asyncpg


class InsufficientFunds(Exception):
    def __init__(self, balance: Decimal, amount: Decimal):
        super().__init__(f"Balance {balance} < {amount}")
        self.balance = balance
        self.amount = amount


async def execute_transfer(
    conn: asyncpg.Connection,
    from_account: str,
    to_account: str,
    amount: Decimal,
    transaction_id: str,
) -> None:
    """Move funds and mark the transaction confirmed, atomically.

    Takes a connection rather than the pool so the caller can run it inside its own
    transaction (the confirm route holds a row lock on the transaction record). When
    nested, conn.transaction() becomes a savepoint, so a raised InsufficientFunds
    leaves nothing behind and the caller can still record the failure.
    """
    async with conn.transaction():
        # Lock rows in consistent order to prevent deadlocks
        for acc_id in sorted([from_account, to_account]):
            await conn.fetchrow("SELECT id FROM accounts WHERE id = $1 FOR UPDATE", acc_id)

        balance = await conn.fetchval("SELECT balance FROM accounts WHERE id = $1", from_account)
        if balance < amount:
            raise InsufficientFunds(balance, amount)

        await conn.execute(
            "UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_account
        )
        await conn.execute(
            "UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to_account
        )
        await conn.execute(
            "UPDATE transactions SET status = 'confirmed', confirmed_at = now(), otp_hash = NULL "
            "WHERE id = $1",
            transaction_id,
        )
