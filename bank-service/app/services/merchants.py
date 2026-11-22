"""Merchant keys and registry lookups.

A merchant authenticates with ``Authorization: Bearer mk_...``. Only the
SHA-256 of the key is stored: the key is 32 random bytes, so a fast hash is
enough (there's nothing to brute-force), and it lets the key be looked up
directly. The plaintext is shown once, when it's issued.
"""

from __future__ import annotations

import hashlib
import secrets

KEY_PREFIX = "mk_"


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def bearer_key(authorization: str | None) -> str | None:
    """The mk_ key from an Authorization header, or None if there isn't one."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token.startswith(KEY_PREFIX):
        return None
    return token


async def merchant_for_key(pool, key: str):
    return await pool.fetchrow("SELECT * FROM merchants WHERE api_key_hash = $1", hash_key(key))
