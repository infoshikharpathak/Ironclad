"""Structured JSON logs that LogScribe reads (one JSON object per line).

Each line has timestamp, service_name, level, message and, when known,
request_id, endpoint, method, status_code, duration_ms and error_type, plus a
stack_trace for exceptions. Lines go to stdout and to
``$IRONCLAD_LOG_DIR/<service>.log`` (default ``./logs``).

Only metadata is logged: never request or response bodies, user messages or
model replies. Messages and stack traces are also scrubbed on the way out
(keys, bearer tokens, OTP-like 6-digit codes, database passwords), and
account numbers are cut to their last 4 digits. That scrubbing is a backstop;
callers still log codes and IDs, not content.

This file is kept identical in bank-service and agent-service
(agent-service/tests/test_logs.py checks it).
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER_NAME = "ironclad"

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("ironclad_request_id", default=None)
endpoint_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("ironclad_endpoint", default=None)

# Extra fields a log call may pass (logger.error(..., extra={...})); anything
# else in `extra` is dropped, so a stray object can't end up in the log.
FIELDS = ("request_id", "endpoint", "method", "status_code", "duration_ms", "error_type",
          "tool", "violation", "provider", "attempts", "merchant_id")


def _mask_account(digits_or_id: str) -> str:
    digits = re.sub(r"\D", "", digits_or_id)
    tail = digits[-4:] if len(digits) >= 4 else digits_or_id[-4:]
    return f"****{tail}"


_SCRUB: list[tuple[re.Pattern[str], Any]] = [
    # Ironclad merchant/policy keys, FoodDash A2A keys, Garrison app keys (gk_, and bk_ from before the rename), OpenAI and Anthropic keys.
    (re.compile(r"\b(mk|pk|ak|gk|bk)_[A-Za-z0-9_\-]{4,}"), lambda m: f"{m.group(1)}_[redacted]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-*.]{4,}"), "sk-[redacted]"),
    (re.compile(r"(?i)\bbearer\s+[^\s'\"]+"), "Bearer [redacted]"),
    (re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token|otp(?:_code)?)(['\"]?\s*[=:]\s*['\"]?)[^\s'\",}]+"),
     lambda m: f"{m.group(1)}{m.group(2)}[redacted]"),
    (re.compile(r"(postgres(?:ql)?://)[^\s@/]+@"), r"\1[redacted]@"),
    # Account numbers: ACC-10042-CHK, acc_demo_user_checking, or a long digit run.
    (re.compile(r"\bACC-\d+-[A-Z]+\b"), lambda m: _mask_account(m.group(0))),
    (re.compile(r"\bacc_[A-Za-z0-9_]+"), lambda m: _mask_account(m.group(0))),
    (re.compile(r"(?<![\d.])\d{8,}(?![\d.])"), lambda m: _mask_account(m.group(0))),
    # OTP-like codes: a standalone 6-digit number.
    (re.compile(r"(?<![\d.,$])\d{6}(?![\d.,])"), "******"),
]


def scrub(text: str) -> str:
    for pattern, repl in _SCRUB:
        text = pattern.sub(repl, text)
    return text


class JSONFormatter(logging.Formatter):
    """One JSON object per line: the contract LogScribe reads."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "service_name": self.service_name,
            "level": record.levelname,
            "message": scrub(record.getMessage()),
        }
        defaults = {"request_id": request_id_var.get(), "endpoint": endpoint_var.get()}
        for field in FIELDS:
            value = getattr(record, field, None)
            if value is None:
                value = defaults.get(field)
            if value is not None:
                payload[field] = scrub(value) if isinstance(value, str) else value
        if record.exc_info and record.exc_info[0] is not None:
            payload["stack_trace"] = scrub(self.formatException(record.exc_info))[-8000:]
            payload.setdefault("error_type", record.exc_info[0].__name__)
        return json.dumps(payload, default=str)


def configure(service_name: str, log_dir: str | Path | None = None) -> logging.Logger:
    """Send the "ironclad" logger to stdout and <log_dir>/<service_name>.log.
    Calling it again replaces the handlers (tests point it at a temp dir)."""
    log_dir = Path(log_dir or os.getenv("IRONCLAD_LOG_DIR") or "./logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    formatter = JSONFormatter(service_name)
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_dir / f"{service_name}.log")):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def route_of(request: Any) -> str:
    """The route template (/transfers/{transfer_id}/confirm), not the raw
    path, so IDs and account numbers in URLs never reach the log."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or scrub(request.url.path)


def _is_database_error(exc: BaseException) -> bool:
    module = type(exc).__module__ or ""
    return module.startswith("asyncpg") or isinstance(exc, (ConnectionError, OSError))


def _is_llm_error(exc: BaseException) -> bool:
    module = type(exc).__module__ or ""
    return module.startswith(("openai", "anthropic"))


def describe_exception(exc: BaseException) -> tuple[str, dict[str, Any]]:
    """A log message and extra fields for an exception (no request content)."""
    name = type(exc).__name__
    detail = scrub(str(exc))[:300]
    if _is_llm_error(exc):
        provider = (type(exc).__module__ or "").split(".")[0]
        status = getattr(exc, "status_code", None)
        what = f"status {status}" if status else "no response"
        return f"LLM provider error ({provider}, {what}): {name}: {detail}", {"provider": provider}
    if _is_database_error(exc):
        return f"Database error: {name}: {detail}", {}
    return f"Unhandled exception: {name}: {detail}", {}


def install_request_logging(app: Any) -> None:
    """Request-ID middleware: reuse a well-formed X-Request-ID or make one,
    log one line per request (method, route, status, duration), and log
    unhandled exceptions with their stack trace before re-raising them."""
    logger = get_logger()

    @app.middleware("http")
    async def request_context(request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        rid_token = request_id_var.set(request_id)
        # Lines logged inside the handler get the path now (scrubbed); the
        # request line below uses the route template once routing has run.
        ep_token = endpoint_var.set(scrub(request.url.path))
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                message, extra = describe_exception(exc)
                logger.error(message, exc_info=exc, extra={
                    "endpoint": route_of(request), "method": request.method, "status_code": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1), **extra})
                raise
            response.headers["X-Request-ID"] = request_id
            logger.info("request completed", extra={
                "endpoint": route_of(request), "method": request.method, "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1)})
            return response
        finally:
            endpoint_var.reset(ep_token)
            request_id_var.reset(rid_token)
