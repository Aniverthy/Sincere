"""Auth and scope-enforcement tests.

§24 lists under "Security": "Auth-scope enforcement (waitlisted token cannot reach
matching/chat)". That is the headline test in this file — it protects the §5 rule that token
scopes mirror lifecycle state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from sincere.shared.auth import (
    CHAT_SCOPES,
    MATCHING_SCOPES,
    QUEUE_SCOPES,
    Scope,
    create_access_token,
    create_refresh_token,
    hash_phone,
    hash_token,
    principal_from_token,
    require_scopes,
)
from sincere.shared.config import get_settings
from sincere.shared.errors import ProblemException


class TestTokenMinting:
    def test_access_token_round_trips(self) -> None:
        token = create_access_token(
            "user-1", Scope.ACTIVE, gender="female", region="8928308280fffff"
        )
        principal = principal_from_token(token)
        assert principal.user_id == "user-1"
        assert principal.scope is Scope.ACTIVE
        assert principal.gender == "female"
        assert principal.is_active

    def test_access_token_expires_in_fifteen_minutes(self) -> None:
        """§5: "short-lived access JWT (~15 min)"."""
        settings = get_settings()
        assert settings.jwt_access_ttl == 900

        token = create_access_token("user-1", Scope.ACTIVE)
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
        lifetime = claims["exp"] - claims["iat"]
        assert lifetime == 900

    def test_refresh_ttl_matches_activity_window(self) -> None:
        """§5 ties the ~30-day refresh to the FR-2.3 activity-window definition."""
        assert get_settings().jwt_refresh_ttl == 30 * 24 * 60 * 60

    def test_expired_token_is_rejected(self) -> None:
        settings = get_settings()
        past = datetime.now(UTC) - timedelta(hours=1)
        token = jwt.encode(
            {
                "sub": "user-1",
                "scope": "active",
                "typ": "access",
                "iss": settings.jwt_issuer,
                "iat": past,
                "exp": past + timedelta(minutes=15),
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(ProblemException) as exc:
            principal_from_token(token)
        assert exc.value.status == 401

    def test_tampered_token_is_rejected(self) -> None:
        token = create_access_token("user-1", Scope.ONBOARDING)
        header, payload, _ = token.split(".")
        forged = f"{header}.{payload}.deadbeef"
        with pytest.raises(ProblemException):
            principal_from_token(forged)

    def test_token_signed_with_another_secret_is_rejected(self) -> None:
        forged = jwt.encode(
            {
                "sub": "attacker",
                "scope": "admin",
                "typ": "access",
                "iss": get_settings().jwt_issuer,
                "exp": datetime.now(UTC) + timedelta(hours=1),
            },
            "a-different-secret",
            algorithm="HS256",
        )
        with pytest.raises(ProblemException):
            principal_from_token(forged)

    def test_refresh_token_cannot_authenticate_a_request(self) -> None:
        """A refresh token presented as a bearer token must be refused, not honored."""
        settings = get_settings()
        token = jwt.encode(
            {
                "sub": "user-1",
                "scope": "active",
                "typ": "refresh",
                "iss": settings.jwt_issuer,
                "exp": datetime.now(UTC) + timedelta(days=1),
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(ProblemException, match="refresh token"):
            principal_from_token(token)

    def test_refresh_tokens_are_opaque_and_unique(self) -> None:
        """§5 needs server-side family revocation, which a self-contained JWT cannot do."""
        first, family = create_refresh_token("user-1")
        second, same_family = create_refresh_token("user-1", family)
        assert first != second
        assert same_family == family
        assert "." not in first  # not a JWT


class TestScopeEnforcement:
    """§24 Security: "waitlisted token cannot reach matching/chat"."""

    @pytest.mark.parametrize("scope", [Scope.WAITLISTED, Scope.ONBOARDING, Scope.PENDING_REVIEW])
    async def test_non_active_scopes_cannot_reach_matching(self, scope: Scope) -> None:
        dependency = require_scopes(*MATCHING_SCOPES)
        principal = principal_from_token(create_access_token("user-1", scope))
        with pytest.raises(ProblemException) as exc:
            await dependency(principal)
        # 403 not 401: the caller IS authenticated, just not eligible.
        assert exc.value.status == 403

    @pytest.mark.parametrize("scope", [Scope.WAITLISTED, Scope.ONBOARDING, Scope.PENDING_REVIEW])
    async def test_non_active_scopes_cannot_reach_chat(self, scope: Scope) -> None:
        dependency = require_scopes(*CHAT_SCOPES)
        principal = principal_from_token(create_access_token("user-1", scope))
        with pytest.raises(ProblemException) as exc:
            await dependency(principal)
        assert exc.value.status == 403

    async def test_active_scope_reaches_matching_and_chat(self) -> None:
        principal = principal_from_token(create_access_token("user-1", Scope.ACTIVE))
        assert await require_scopes(*MATCHING_SCOPES)(principal) is principal
        assert await require_scopes(*CHAT_SCOPES)(principal) is principal

    async def test_waitlisted_scope_reaches_queue_and_auction(self) -> None:
        """FR-2.8/2.9: a waitlisted man must be able to pay or bid his way in — that is the
        entire paid/auction tier. Denying queue routes would break the product."""
        principal = principal_from_token(create_access_token("user-1", Scope.WAITLISTED))
        assert await require_scopes(*QUEUE_SCOPES)(principal) is principal

    async def test_ordinary_user_cannot_reach_admin(self) -> None:
        principal = principal_from_token(create_access_token("user-1", Scope.ACTIVE))
        with pytest.raises(ProblemException) as exc:
            await require_scopes(Scope.ADMIN)(principal)
        assert exc.value.status == 403

    async def test_admin_scope_is_not_a_superuser_for_product_routes(self) -> None:
        """An admin token is for FR-8 ops surfaces, not a bypass of the product lifecycle."""
        principal = principal_from_token(create_access_token("ops-1", Scope.ADMIN))
        with pytest.raises(ProblemException):
            await require_scopes(*MATCHING_SCOPES)(principal)


class TestHashing:
    def test_phone_is_hashed_deterministically(self) -> None:
        """§8 stores ``phone_hash``; the raw number never lands in the database."""
        assert hash_phone("+919876543210") == hash_phone("+919876543210")
        assert hash_phone("+919876543210") != hash_phone("+919876543211")

    def test_phone_hash_ignores_surrounding_whitespace(self) -> None:
        assert hash_phone(" +919876543210 ") == hash_phone("+919876543210")

    def test_phone_hash_is_keyed_not_plain(self) -> None:
        """A plain SHA-256 of a 10-digit space is trivially reversible; §18's posture
        requires that a database leak alone is not enough."""
        import hashlib

        phone = "+919876543210"
        assert hash_phone(phone) != hashlib.sha256(phone.encode()).hexdigest()

    def test_refresh_tokens_are_stored_hashed(self) -> None:
        token, _ = create_refresh_token("user-1")
        stored = hash_token(token)
        assert stored != token
        assert hash_token(token) == stored


def test_scope_values_cover_the_lifecycle_states() -> None:
    """§6 lifecycle states must each have a representable scope."""
    assert {str(s) for s in Scope} >= {
        "onboarding",
        "pending_review",
        "waitlisted",
        "active",
    }
