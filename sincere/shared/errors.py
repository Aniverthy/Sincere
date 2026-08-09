"""Error model — cross-cutting plumbing only, no business logic.

TECHNICAL_IMPLEMENTATION_PLAN.md §7:391 specifies **RFC-7807 problem+json** for every error
response. This module provides the exception type, the FastAPI handlers that render it, and
named subclasses for the recurring domain failures so routes raise intent rather than status codes.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/problem+json"


class ProblemException(Exception):
    """An error renderable as RFC-7807 ``application/problem+json``."""

    def __init__(
        self,
        *,
        status: int,
        title: str,
        detail: str | None = None,
        type_: str = "about:blank",
        instance: str | None = None,
        **extensions: Any,
    ) -> None:
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type_
        self.instance = instance
        self.extensions = extensions
        super().__init__(detail or title)

    def to_dict(self, instance: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
        }
        if self.detail:
            body["detail"] = self.detail
        if inst := (self.instance or instance):
            body["instance"] = inst
        body.update(self.extensions)
        return body


# ---------------------------------------------------------------------------
# Named domain failures
# ---------------------------------------------------------------------------

class NotFoundError(ProblemException):
    def __init__(self, resource: str, detail: str | None = None) -> None:
        super().__init__(
            status=status.HTTP_404_NOT_FOUND,
            title=f"{resource} not found",
            detail=detail,
            type_="/errors/not-found",
        )


class ConflictError(ProblemException):
    def __init__(self, title: str, detail: str | None = None) -> None:
        super().__init__(
            status=status.HTTP_409_CONFLICT, title=title, detail=detail, type_="/errors/conflict"
        )


class ValidationError(ProblemException):
    def __init__(self, detail: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation failed",
            detail=detail,
            type_="/errors/validation",
            errors=errors or [],
        )


class RateLimitedError(ProblemException):
    def __init__(self, retry_after: int, detail: str | None = None) -> None:
        super().__init__(
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            title="Rate limit exceeded",
            detail=detail or "Too many requests. Retry after the indicated interval.",
            type_="/errors/rate-limited",
            retry_after=retry_after,
        )
        self.retry_after = retry_after


class ForbiddenError(ProblemException):
    def __init__(self, title: str, detail: str | None = None) -> None:
        super().__init__(
            status=status.HTTP_403_FORBIDDEN, title=title, detail=detail, type_="/errors/forbidden"
        )


class PaymentRequiredError(ProblemException):
    """FR-6.3: entry-tier visibility is gated behind a Pro subscription."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            status=status.HTTP_403_FORBIDDEN,
            title="Pro subscription required",
            detail=detail,
            type_="/errors/pro-required",
        )


class ServiceUnavailableError(ProblemException):
    def __init__(self, title: str, detail: str | None = None) -> None:
        super().__init__(
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
            title=title,
            detail=detail,
            type_="/errors/unavailable",
        )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def register_error_handlers(app: FastAPI) -> None:
    """Render every error path as problem+json."""

    @app.exception_handler(ProblemException)
    async def _problem(request: Request, exc: ProblemException) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitedError):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.status,
            content=exc.to_dict(instance=str(request.url.path)),
            media_type=CONTENT_TYPE,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ())),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        problem = ValidationError("The request body or parameters are invalid.", errors)
        return JSONResponse(
            status_code=problem.status,
            content=problem.to_dict(instance=str(request.url.path)),
            media_type=CONTENT_TYPE,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        problem = ProblemException(
            status=exc.status_code,
            title=str(exc.detail) if exc.detail else "Request failed",
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.to_dict(instance=str(request.url.path)),
            media_type=CONTENT_TYPE,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # §22: log the failure with correlation, but never leak internals to the client.
        logger.exception(
            "request.unhandled_error",
            extra={
                "path": str(request.url.path),
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        problem = ProblemException(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal server error",
            detail="An unexpected error occurred. The incident has been logged.",
            type_="/errors/internal",
        )
        return JSONResponse(
            status_code=problem.status,
            content=problem.to_dict(instance=str(request.url.path)),
            media_type=CONTENT_TYPE,
        )
