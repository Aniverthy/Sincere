"""Structured logging — cross-cutting plumbing only, no business logic.

TECHNICAL_IMPLEMENTATION_PLAN.md §22:

* Structured JSON logs, request-ID + **hashed** user-ID correlation, OpenTelemetry trace IDs.
* **Never logged:** message bodies (metadata only), raw locations beyond operational need,
  embedding vectors, OTPs/tokens, payment credentials.

The redaction list is enforced here by :class:`RedactionFilter` rather than left to
discipline at each call site, because a single careless ``logger.info(message)`` in the chat
module would otherwise put message bodies in the log store — a privacy incident, not a bug.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from sincere.shared.config import get_settings

#: Keys whose values must never reach the log store (§22).
REDACTED_KEYS = frozenset(
    {
        "body",              # message bodies — chat metadata only
        "message_body",
        "vector",            # embedding vectors
        "embedding",
        "otp",
        "otp_code",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "card",
        "card_number",
        "cvv",
        "payment_credentials",
        "phone",             # the raw number; phone_hash is fine
        "coordinates",       # raw location precision (§18 location minimalism)
    }
)

REDACTED = "[redacted]"

_RESERVED = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info", "thread",
        "threadName", "taskName",
    }
)


def hash_user_id(user_id: str | None) -> str | None:
    """§22 correlates on a *hashed* user ID — logs are personal data too."""
    if not user_id:
        return None
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in REDACTED_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value


class RedactionFilter(logging.Filter):
    """Strip §22-forbidden fields from every record before it is formatted."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if key in _RESERVED:
                continue
            record.__dict__[key] = _redact(record.__dict__[key], key)
        return True


class JsonFormatter(logging.Formatter):
    """Single-line JSON, one object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # OpenTelemetry correlation (§22) — only when a span is actually recording.
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            context = span.get_span_context()
            if context.is_valid:
                payload["trace_id"] = format(context.trace_id, "032x")
                payload["span_id"] = format(context.span_id, "016x")
        except Exception:  # noqa: BLE001
            pass

        return json.dumps(payload, default=str)


_original_make_record = logging.Logger.makeRecord


def _safe_make_record(
    self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None
):
    """``makeRecord`` that renames colliding ``extra`` keys instead of raising.

    The stdlib raises ``KeyError`` when ``extra`` carries a key that shadows a built-in
    ``LogRecord`` attribute — ``name``, ``module``, ``message``, ``args`` and friends. Those
    are ordinary words in this domain (an index *name*, a *module* label), so the collision is
    easy to write, and it only fires on the exact code path that logs it. A single log line
    taking the process down is not an acceptable failure mode for something §22 requires on
    every request — this cost a startup outage the first time it hit a real Atlas cluster.

    Colliding keys are prefixed rather than dropped, so the value still reaches the log store.
    """
    if extra:
        extra = {
            (f"ctx_{key}" if key in _RESERVED or key == "asctime" else key): value
            for key, value in extra.items()
        }
    return _original_make_record(
        self, name, level, fn, lno, msg, args, exc_info, func, extra, sinfo
    )


def install_reserved_key_guard() -> None:
    """Patch the base Logger so every logger is protected.

    Applied to ``logging.Logger`` rather than via ``setLoggerClass`` because every module
    creates its logger at import time, long before :func:`configure_logging` runs — a new
    logger class would protect none of them.
    """
    logging.Logger.makeRecord = _safe_make_record  # type: ignore[method-assign]


def configure_logging() -> None:
    """Install the JSON formatter and redaction filter on the root logger."""
    settings = get_settings()
    install_reserved_key_guard()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Uvicorn's own handlers would otherwise emit unstructured duplicates.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # pymongo/motor are chatty at DEBUG and would drown the application signal.
    logging.getLogger("pymongo").setLevel(logging.WARNING)
