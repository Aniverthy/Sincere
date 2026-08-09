"""Shared pytest fixtures.

Unit and property tests run entirely in-memory (mongomock-motor + fakeredis) so the suite
needs no infrastructure. Tests marked ``integration`` require a live Atlas cluster and Redis —
TECHNICAL_IMPLEMENTATION_PLAN.md §24 places the signup/vector-search and deletion-cascade
suites there deliberately, because mocking Atlas Vector Search would test the mock.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-any-real-deployment")


def pytest_configure() -> None:
    """Stop the test suite reading the developer's local ``.env``.

    ``Settings`` and ``Thresholds`` load ``.env`` by default, which means a value someone set
    for their own machine — a dev-only feature flag, a different threshold — silently changes
    what the tests assert. That already bit once: enabling DEV_AUTO_APPROVE_VERIFICATION
    locally broke an unrelated production-guard test.

    Tests should depend only on documented defaults and what they pass explicitly.
    """
    from sincere.shared.config import Settings, Thresholds

    for model in (Settings, Thresholds):
        model.model_config["env_file"] = None


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Settings and thresholds are LRU-cached for the process lifetime; tests that tweak
    environment variables need that cache cleared or they leak into each other."""
    from sincere.shared.config import get_default_thresholds, get_settings

    get_settings.cache_clear()
    get_default_thresholds.cache_clear()
    yield
    get_settings.cache_clear()
    get_default_thresholds.cache_clear()


@pytest.fixture
async def database() -> AsyncIterator[object]:
    """In-memory MongoDB standing in for Atlas."""
    from mongomock_motor import AsyncMongoMockClient

    from sincere.shared import db as db_module

    client = AsyncMongoMockClient()
    database = client["sincere_test"]

    db_module._database = database  # noqa: SLF001 — test seam
    db_module._client = client  # noqa: SLF001
    try:
        yield database
    finally:
        db_module._database = None  # noqa: SLF001
        db_module._client = None  # noqa: SLF001


@pytest.fixture
async def redis_client() -> AsyncIterator[object]:
    """In-memory Redis standing in for the §16 cache."""
    import fakeredis.aioredis

    from sincere.shared import cache as cache_module

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_module._client = client  # noqa: SLF001 — test seam
    try:
        yield client
    finally:
        await client.aclose()
        cache_module._client = None  # noqa: SLF001


@pytest.fixture
def thresholds():
    """Launch-default thresholds — the documented values, not test-invented ones."""
    from sincere.shared.config import get_default_thresholds

    return get_default_thresholds()


@pytest.fixture
def event_bus() -> Iterator[object]:
    """A clean bus per test. The application bus is a module-level singleton, so handlers
    registered by one test would otherwise fire in the next."""
    from sincere.shared.events import EventBus

    yield EventBus()
