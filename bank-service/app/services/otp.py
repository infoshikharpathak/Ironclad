import random

import bcrypt

_rng = random.SystemRandom()

# 6-digit codes with a 3-attempt cap don't need bcrypt's default cost; 10 keeps
# hashing around ~50ms. Callers should still run these via asyncio.to_thread.
_BCRYPT_ROUNDS = 10


def generate_otp() -> str:
    return f"{_rng.randrange(0, 1_000_000):06d}"


def hash_otp(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_otp(code: str, otp_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode(), otp_hash.encode())
    except ValueError:
        return False
