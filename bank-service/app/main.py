import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .db import init_pool, close_pool
from .errors import BankError
from .routes import health, accounts, transfers, directory, payments, policies
from .ws.notifications import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("bank-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to database …")
    await init_pool()
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


# --- Global error handler for BankError ---
@app.exception_handler(BankError)
async def bank_error_handler(_request: Request, exc: BankError):
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
