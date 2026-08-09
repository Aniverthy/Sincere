"""HTTP middleware — cross-cutting plumbing only, no business logic.

Supplies the request-ID correlation that TECHNICAL_IMPLEMENTATION_PLAN.md §22 requires
("request-ID + user-ID (hashed) correlation") and the per-route latency histogram §21 alerts on
("API latency p50/p95/p99 per route").
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from sincere.shared.config import get_settings
from sincere.shared.logging import hash_user_id

logger = logging.getLogger(__name__)

REQUEST_LATENCY = Histogram(
    "sincere_request_duration_seconds",
    "Request latency per route (§21: p50/p95/p99 per route)",
    labelnames=("method", "route", "status"),
    # Buckets chosen around the §2 targets: p95 < 300ms interactive, < 150ms swipe writes.
    buckets=(0.025, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0, 10.0),
)

REQUEST_COUNT = Counter(
    "sincere_requests_total",
    "Total requests per route and status",
    labelnames=("method", "route", "status"),
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID, log completion, and record §21 metrics."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        request.state.user_id = None

        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            self._observe(request, 500, time.perf_counter() - started)
            raise

        elapsed = time.perf_counter() - started
        response.headers["X-Request-ID"] = request_id
        self._observe(request, response.status_code, elapsed)

        logger.info(
            "request.completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "route": self._route(request),
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
                # §22: correlate on the HASHED user id — logs are personal data too
                "user_hash": hash_user_id(getattr(request.state, "user_id", None)),
            },
        )
        return response

    @staticmethod
    def _route(request: Request) -> str:
        """Templated path (``/v1/matches/{match_id}``) so metrics do not explode per-id."""
        route = request.scope.get("route")
        return getattr(route, "path", request.url.path)

    def _observe(self, request: Request, status_code: int, elapsed: float) -> None:
        if not get_settings().metrics_enabled:
            return
        labels = (request.method, self._route(request), str(status_code))
        REQUEST_LATENCY.labels(*labels).observe(elapsed)
        REQUEST_COUNT.labels(*labels).inc()


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
