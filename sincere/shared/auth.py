"""Authentication — cross-cutting plumbing only, no business logic.

Implements TECHNICAL_IMPLEMENTATION_PLAN.md §5 token rules:

* Short-lived access JWT (~15 min), rotating refresh (~30 days, matching the activity window).
* **Token scopes mirror lifecycle state** — ``onboarding`` -> ``waitlisted`` -> ``active``.
  A waitlisted man's token cannot call matching or chat endpoints. This is enforced here,
  not in each route, so the guarantee cannot be forgotten.
* Refresh rotation with **reuse detection**: replaying a refresh token revokes the whole family.
* WebSocket auth: the access JWT is presented at connect; the connection drops on expiry.

Issuing tokens is the identity module's job. This module only *mints, verifies and enforces*.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any
from uuid import uuid4

import jwt
from fastapi import Depends, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sincere.shared.config import get_settings
from sincere.shared.errors import ProblemException

logger = logging.getLogger(__name__)


class Scope(StrEnum):
    """Token scopes, mirroring the §6 lifecycle states."""

    ONBOARDING = "onboarding"
    """Signup complete, verification not finished. May only reach profile + verification routes."""

    PENDING_REVIEW = "pending_review"
    """Bot-risk ambiguous band (FR-1.6). Read-only status polling."""

    WAITLISTED = "waitlisted"
    """Verified man in a frozen/at-ceiling hex. May reach queue, auction and payment routes —
    explicitly NOT matching or chat (§5)."""

    ACTIVE = "active"
    """Admitted. Full product surface."""

    ADMIN = "admin"
    """Ops/founder. Admin routes only (FR-8)."""


#: Which scopes may reach which surface. Encoded once, enforced by the dependencies below.
MATCHING_SCOPES = frozenset({Scope.ACTIVE})
CHAT_SCOPES = frozenset({Scope.ACTIVE})
QUEUE_SCOPES = frozenset({Scope.WAITLISTED, Scope.ACTIVE})
PROFILE_SCOPES = frozenset({Scope.ONBOARDING, Scope.PENDING_REVIEW, Scope.WAITLISTED, Scope.ACTIVE})
VERIFICATION_SCOPES = frozenset({Scope.ONBOARDING, Scope.PENDING_REVIEW})


@dataclass(slots=True, frozen=True)
class Principal:
    """The authenticated caller."""

    user_id: str
    scope: Scope
    gender: str | None = None
    region: str | None = None
    token_id: str | None = None

    @property
    def is_active(self) -> bool:
        return self.scope is Scope.ACTIVE


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def hash_phone(phone: str) -> str:
    """Deterministic phone hash — §8 stores ``phone_hash``, never the raw number.

    Keyed with the JWT secret so a database leak alone does not permit a rainbow-table
    reversal of a 10-digit number space.
    """
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, phone.strip().encode(), hashlib.sha256).hexdigest()


def hash_token(token: str) -> str:
    """Refresh tokens are stored hashed — the database never holds a usable credential."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Token minting & verification
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    scope: Scope,
    *,
    gender: str | None = None,
    region: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": user_id,
        "scope": str(scope),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_access_ttl),
        "jti": str(uuid4()),
    }
    if gender:
        claims["gender"] = gender
    if region:
        claims["region"] = region
    if extra:
        claims.update(extra)
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, family_id: str | None = None) -> tuple[str, str]:
    """Mint an opaque refresh token. Returns ``(token, family_id)``.

    Opaque rather than a JWT because §5 requires server-side revocation of a whole family
    on reuse — a self-contained token cannot be revoked.
    """
    return secrets.token_urlsafe(48), family_id or str(uuid4())


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise ProblemException(
            status=status.HTTP_401_UNAUTHORIZED,
            title="Token expired",
            detail="The access token has expired. Refresh and retry.",
            type_="/errors/token-expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise ProblemException(
            status=status.HTTP_401_UNAUTHORIZED,
            title="Invalid token",
            detail="The access token could not be verified.",
            type_="/errors/invalid-token",
        ) from exc


def principal_from_token(token: str) -> Principal:
    claims = decode_token(token)
    if claims.get("typ") != "access":
        raise ProblemException(
            status=status.HTTP_401_UNAUTHORIZED,
            title="Wrong token type",
            detail="A refresh token cannot be used to authenticate a request.",
            type_="/errors/invalid-token",
        )
    try:
        scope = Scope(claims["scope"])
    except (KeyError, ValueError) as exc:
        raise ProblemException(
            status=status.HTTP_401_UNAUTHORIZED,
            title="Invalid token",
            detail="Token carries no recognizable scope.",
            type_="/errors/invalid-token",
        ) from exc

    return Principal(
        user_id=claims["sub"],
        scope=scope,
        gender=claims.get("gender"),
        region=claims.get("region"),
        token_id=claims.get("jti"),
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> Principal:
    if credentials is None:
        raise ProblemException(
            status=status.HTTP_401_UNAUTHORIZED,
            title="Not authenticated",
            detail="This endpoint requires a bearer access token.",
            type_="/errors/not-authenticated",
        )
    principal = principal_from_token(credentials.credentials)
    request.state.user_id = principal.user_id
    return principal


def require_scopes(*allowed: Scope):
    """Dependency factory enforcing the §5 scope rules.

    Usage::

        @router.get("/matches/daily", dependencies=[Depends(require_scopes(*MATCHING_SCOPES))])
    """
    permitted = frozenset(allowed)

    async def dependency(
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> Principal:
        if principal.scope not in permitted:
            # §24 security test asserts exactly this: a waitlisted token cannot reach
            # matching or chat. 403 (not 401) — the caller is authenticated, just not eligible.
            logger.warning(
                "auth.scope_denied",
                extra={
                    "user_id": principal.user_id,
                    "scope": str(principal.scope),
                    "required": sorted(str(s) for s in permitted),
                },
            )
            raise ProblemException(
                status=status.HTTP_403_FORBIDDEN,
                title="Insufficient scope",
                detail=(
                    f"Your account state ('{principal.scope}') does not permit this action. "
                    f"Requires one of: {', '.join(sorted(str(s) for s in permitted))}."
                ),
                type_="/errors/insufficient-scope",
            )
        return principal

    return dependency


require_active = require_scopes(Scope.ACTIVE)
require_admin = require_scopes(Scope.ADMIN)


async def principal_from_websocket(websocket: WebSocket) -> Principal | None:
    """Authenticate a WebSocket at connect (§5).

    Accepts the token from the ``Authorization`` header or a ``token`` query parameter —
    React Native's WebSocket cannot set headers, so the query parameter is the real path.
    Returns ``None`` when authentication fails; the caller closes the socket.
    """
    token = websocket.query_params.get("token")
    if not token:
        header = websocket.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:]
    if not token:
        return None
    try:
        principal = principal_from_token(token)
    except ProblemException:
        return None
    return principal if principal.scope in CHAT_SCOPES else None
