"""Policy-access keys: who may read which levels of policy documents.

A caller sends 'Authorization: Bearer pk_...'. The key maps to its allowed
levels (public, or public and internal). Access never comes from the request
itself. Only the SHA-256 of a key is stored; the key is shown once.
"""

from __future__ import annotations

import hashlib
import secrets

KEY_PREFIX = "pk_"


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def bearer_key(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token.startswith(KEY_PREFIX):
        return None
    return token


async def levels_for(pool, key: str) -> list[str] | None:
    """The levels *key* may read, or None if it's unknown or revoked."""
    row = await pool.fetchrow(
        "SELECT levels FROM policy_access_keys WHERE key_hash = $1 AND revoked_at IS NULL", hash_key(key))
    return list(row["levels"]) if row else None


async def create(conn, name: str, levels: list[str]) -> str:
    key = new_key()
    await conn.execute("INSERT INTO policy_access_keys (name, key_hash, levels) VALUES ($1, $2, $3)",
                       name, hash_key(key), levels)
    return key
