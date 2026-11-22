"""Ironclad bank admin CLI. Run from bank-service/ (uses DATABASE_URL):

    python -m app.cli migrate
        Apply db/002_merchants.sql and db/003_policies.sql to an existing
        database (idempotent).
    python -m app.cli policy-keys create <name> --levels public[,internal]
        Issues a policy-access key (pk_...) for GET /policies/search, printed once.
    python -m app.cli policy-keys list | revoke <name>
    python -m app.cli index-policies [--dry-run]
        Chunk bank-service/policies/*.md, embed changed chunks, drop removed ones.
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

DB_DIR = Path(__file__).resolve().parents[2] / "db"
MIGRATIONS = ["002_merchants.sql", "003_policies.sql", "004_policy_hybrid.sql", "005_policy_access.sql", "006_transfer_flags.sql"]  # init.sql is the base schema
_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(config.DATABASE_URL)


async def migrate() -> None:
    conn = await _connect()
    try:
        for name in MIGRATIONS:
            await conn.execute((DB_DIR / name).read_text())
            print(f"Applied {name}")
    finally:
        await conn.close()


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


async def index_policies(dry_run: bool, max_tokens: int | None) -> None:
    from .policies import chunking, embeddings, store

    chunks = chunking.load_policies(max_tokens=max_tokens or chunking.DEFAULT_MAX_TOKENS)
    embedder = embeddings.default_embedder()
    if embedder is None:
        if not dry_run:
            sys.exit("OPENAI_API_KEY is not set (needed to embed the policies)")
        embedder = embeddings.FakeEmbedder()  # only hashes are compared in a dry run
    conn = await _connect()
    try:
        report = await store.index_chunks(conn, chunks, embedder, dry_run=dry_run)
    finally:
        await conn.close()
    docs = len({c.doc_slug for c in chunks})
    verb = "would embed" if dry_run else "embedded"
    print(f"{report.total} chunks from {docs} documents: {verb} {report.embedded}, "
          f"{report.unchanged} unchanged, {'would remove' if dry_run else 'removed'} {report.removed}")
    if not dry_run:
        print(f"Embedding: {embedder.model}, {report.tokens} tokens, cost ${report.cost_usd}")


async def policy_keys(action: str, name: str | None, levels: str | None) -> None:
    from .policies import access

    conn = await _connect()
    try:
        if action == "list":
            for r in await conn.fetch("SELECT name, levels, created_at, revoked_at FROM policy_access_keys ORDER BY name"):
                state = f"revoked {r['revoked_at']:%Y-%m-%d}" if r["revoked_at"] else "active"
                print(f"{r['name']:<24} {','.join(r['levels']):<18} {state}")
        elif action == "create":
            wanted = [lv.strip() for lv in (levels or "").split(",") if lv.strip()]
            if not wanted or not set(wanted) <= {"public", "internal"}:
                sys.exit("--levels must be public, internal or public,internal")
            if "internal" in wanted and "public" not in wanted:
                wanted.insert(0, "public")  # internal readers can read public documents too
            try:
                key = await access.create(conn, name, wanted)
            except asyncpg.UniqueViolationError:
                sys.exit(f"a policy key named {name!r} already exists")
            print(f"Policy key {name!r} ({', '.join(wanted)}), shown once; only its hash is stored:")
            print(key)
        else:
            done = await conn.execute("UPDATE policy_access_keys SET revoked_at = now() WHERE name = $1 "
                                      "AND revoked_at IS NULL", name)
            if done == "UPDATE 0":
                sys.exit(f"no active policy key named {name!r}")
            print(f"{name}: revoked")
    finally:
        await conn.close()


def _print_key(merchant_id: str, key: str) -> None:
    print(f"Merchant key for {merchant_id} (shown once; only its hash is stored):")
    print(key)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Ironclad bank admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply db/002_merchants.sql and db/003_policies.sql (idempotent)")
    pk = sub.add_parser("policy-keys", help="manage policy-access keys").add_subparsers(dest="action", required=True)
    pkc = pk.add_parser("create")
    pkc.add_argument("name")
    pkc.add_argument("--levels", required=True, help="public or public,internal")
    pk.add_parser("list")
    pkr = pk.add_parser("revoke")
    pkr.add_argument("name")
    ix = sub.add_parser("index-policies", help="embed bank-service/policies/*.md into policy_chunks")
    ix.add_argument("--dry-run", action="store_true", help="only report what would change")
    ix.add_argument("--max-tokens", type=int, default=None,
                    help="split sections longer than this (est. tokens; default chunking.DEFAULT_MAX_TOKENS)")
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
    elif args.cmd == "policy-keys":
        coro = policy_keys(args.action, getattr(args, "name", None), getattr(args, "levels", None))
    elif args.cmd == "index-policies":
        coro = index_policies(args.dry_run, args.max_tokens)
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
