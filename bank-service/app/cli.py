"""Ironclad bank admin CLI. Run from bank-service/ (uses DATABASE_URL):

    python -m app.cli migrate
        Apply db/002_merchants.sql to an existing database (idempotent).
    python -m app.cli merchants list
    python -m app.cli merchants create <merchant_id> "<Display Name>" --limit 200 [--agent-payments]
        Registers a merchant with its own settlement account and prints its key once.
    python -m app.cli merchants issue-key <merchant_id>
        Issues a new key (the old one stops working) and prints it once.
    python -m app.cli merchants set-status <merchant_id> active|suspended
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from decimal import Decimal
from pathlib import Path

import asyncpg

from . import config
from .services import merchants as merchant_keys

MIGRATION = Path(__file__).resolve().parents[2] / "db" / "002_merchants.sql"
_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(config.DATABASE_URL)


async def migrate() -> None:
    conn = await _connect()
    try:
        await conn.execute(MIGRATION.read_text())
    finally:
        await conn.close()
    print(f"Applied {MIGRATION.name}")


async def list_merchants() -> None:
    conn = await _connect()
    try:
        rows = await conn.fetch("SELECT * FROM merchants ORDER BY merchant_id")
    finally:
        await conn.close()
    for r in rows:
        key = "key issued" if r["api_key_hash"] else "no key"
        print(f"{r['merchant_id']:<12} {r['display_name']:<16} {r['status']:<9} limit ${r['max_payment_amount']:<8} "
              f"agent_payments={'yes' if r['agent_payments_allowed'] else 'no':<3} -> {r['settlement_account_id']} ({key})")


async def create_merchant(merchant_id: str, display_name: str, limit: Decimal, agent_payments: bool) -> None:
    if not _ID.match(merchant_id):
        sys.exit("merchant_id must be lowercase letters, digits or _ (2-40 chars, starting with a letter)")
    key = merchant_keys.new_key()
    account_id = f"acc_merchant_{merchant_id}_settlement"
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO accounts (id, user_id, name, account_type, balance, owner_name, is_public)
                   VALUES ($1, $2, $3, 'checking', 0, $4, false)""",
                account_id, f"merchant:{merchant_id}", f"{display_name} settlement", display_name,
            )
            await conn.execute(
                """INSERT INTO merchants (merchant_id, display_name, settlement_account_id, api_key_hash,
                                          max_payment_amount, agent_payments_allowed, status)
                   VALUES ($1, $2, $3, $4, $5, $6, 'active')""",
                merchant_id, display_name, account_id, merchant_keys.hash_key(key), limit, agent_payments,
            )
    except asyncpg.UniqueViolationError:
        sys.exit(f"merchant {merchant_id!r} (or its settlement account) already exists")
    finally:
        await conn.close()
    _print_key(merchant_id, key)


async def issue_key(merchant_id: str) -> None:
    key = merchant_keys.new_key()
    conn = await _connect()
    try:
        done = await conn.execute("UPDATE merchants SET api_key_hash = $1 WHERE merchant_id = $2",
                                  merchant_keys.hash_key(key), merchant_id)
    finally:
        await conn.close()
    if done == "UPDATE 0":
        sys.exit(f"no merchant {merchant_id!r}")
    _print_key(merchant_id, key)


async def set_status(merchant_id: str, status: str) -> None:
    conn = await _connect()
    try:
        done = await conn.execute("UPDATE merchants SET status = $1 WHERE merchant_id = $2", status, merchant_id)
    finally:
        await conn.close()
    if done == "UPDATE 0":
        sys.exit(f"no merchant {merchant_id!r}")
    print(f"{merchant_id}: {status}")


def _print_key(merchant_id: str, key: str) -> None:
    print(f"Merchant key for {merchant_id} (shown once; only its hash is stored):")
    print(key)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Ironclad bank admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply db/002_merchants.sql (idempotent)")
    m = sub.add_parser("merchants", help="manage merchants").add_subparsers(dest="action", required=True)
    m.add_parser("list")
    c = m.add_parser("create")
    c.add_argument("merchant_id")
    c.add_argument("display_name")
    c.add_argument("--limit", type=Decimal, required=True, help="max payment amount in USD")
    c.add_argument("--agent-payments", action="store_true", help="allow channel=agent payment requests")
    k = m.add_parser("issue-key")
    k.add_argument("merchant_id")
    s = m.add_parser("set-status")
    s.add_argument("merchant_id")
    s.add_argument("status", choices=["active", "suspended"])
    args = parser.parse_args(argv)

    if args.cmd == "migrate":
        coro = migrate()
    elif args.action == "list":
        coro = list_merchants()
    elif args.action == "create":
        if args.limit <= 0:
            sys.exit("--limit must be positive")
        coro = create_merchant(args.merchant_id, args.display_name, args.limit, args.agent_payments)
    elif args.action == "issue-key":
        coro = issue_key(args.merchant_id)
    else:
        coro = set_status(args.merchant_id, args.status)
    asyncio.run(coro)


if __name__ == "__main__":
    main()
