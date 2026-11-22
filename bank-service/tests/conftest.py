"""Shared fixtures. Tests that need Postgres use the `bank` fixture: a fresh
schema (db/init.sql + db/002_merchants.sql) inside TEST_DATABASE_URL, dropped
afterwards. Without TEST_DATABASE_URL those tests are skipped."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

DB_DIR = Path(__file__).resolve().parents[2] / "db"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def bank(monkeypatch):
    """(client, pool, pushed): the real app on a throwaway schema."""
    if not TEST_DATABASE_URL:
        pytest.skip("set TEST_DATABASE_URL (a Postgres the tests may create schemas in)")
    import asyncpg
    import httpx

    import app.db as app_db
    import app.main as bank_app
    from app.ws.notifications import manager

    schema = "test_" + uuid.uuid4().hex[:10]
    admin = await asyncpg.connect(TEST_DATABASE_URL)
    await admin.execute(f"CREATE SCHEMA {schema}")
    await admin.execute(f"SET search_path TO {schema}")
    await admin.execute((DB_DIR / "init.sql").read_text())
    await admin.execute((DB_DIR / "002_merchants.sql").read_text())
    pool = await asyncpg.create_pool(TEST_DATABASE_URL, min_size=1, max_size=4,
                                     server_settings={"search_path": schema})
    monkeypatch.setattr(app_db, "_pool", pool)

    pushed: list[tuple[str, dict]] = []

    async def push(user_id, event):
        pushed.append((user_id, event))

    monkeypatch.setattr(manager, "send_to_user", push)
    transport = httpx.ASGITransport(app=bank_app.app)  # no lifespan: the pool above is used
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://bank") as client:
            yield client, pool, pushed
    finally:
        await pool.close()
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()
