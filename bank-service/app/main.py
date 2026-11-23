import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, logs
from .db import init_pool, close_pool
from .errors import BankError
from .routes import health, accounts, transfers, directory, payments, policies
from .ws.notifications import router as ws_router

SERVICE_NAME = "bank-service"
logger = logs.configure(SERVICE_NAME)

# BankError codes logged at ERROR, as incidents LogScribe analyzes: OTP
# failures, limit refusals, merchant API rejections and outages. Other codes
# (not found, an OTP typo with attempts left, ...) are ordinary 4xx: WARNING.
INCIDENT_CODES = frozenset({
    "OTP_EXPIRED", "OTP_MAX_ATTEMPTS",
    "LIMIT_PER_TRANSFER", "LIMIT_DAILY", "AMOUNT_OVER_LIMIT",
    "MERCHANT_KEY_REQUIRED", "MERCHANT_KEY_INVALID", "MERCHANT_SUSPENDED",
    "AGENT_PAYMENTS_NOT_ALLOWED", "PAYEE_NOT_ALLOWED", "SETTLEMENT_ACCOUNT_MISSING",
    "POLICY_KEY_INVALID", "POLICY_SEARCH_UNAVAILABLE",
})


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to database …")
    try:
        await init_pool()
    except Exception as exc:
        message, extra = logs.describe_exception(exc)
        logger.error(message, exc_info=exc, extra=extra)
        raise
    logger.info("Database pool ready")
    yield
    logger.info("Shutting down …")
    await close_pool()


app = FastAPI(title="Ironclad Bank Service", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


logs.install_request_logging(app)


# --- Global error handler for BankError ---
@app.exception_handler(BankError)
async def bank_error_handler(request: Request, exc: BankError):
    endpoint = logs.route_of(request)
    incident = exc.code in INCIDENT_CODES or (endpoint.startswith("/payments") and exc.status_code in (401, 403))
    attempts = exc.details.get("attempts") if isinstance(exc.details, dict) else None
    logger.log(logging.ERROR if incident else logging.WARNING, "%s: %s", exc.code, exc.message, extra={
        "error_type": exc.code, "status_code": exc.status_code, "endpoint": endpoint,
        "method": request.method, "attempts": attempts})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


# --- Routers ---
app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(transfers.router)
app.include_router(directory.router)
app.include_router(payments.router)
app.include_router(policies.router)
app.include_router(ws_router)
