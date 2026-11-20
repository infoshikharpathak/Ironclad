import os
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://anvil:devpassword@localhost:5432/anvil_bank"
)

# OTP lifetime. Lower it (e.g. OTP_TTL_SECONDS=20) to exercise expiry by hand.
OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "300"))
OTP_MAX_ATTEMPTS = 3

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    if origin.strip()
]

# Balances restored by POST /accounts/reset. Must match seed_demo_user() in db/init.sql.
SEED_BALANCES = {"checking": Decimal("10000.00"), "savings": Decimal("5000.00")}
