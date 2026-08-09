"""Application entrypoint — the single deployable of the modular monolith.

Mounts each of the eight module routers onto one FastAPI app, per
TECHNICAL_IMPLEMENTATION_PLAN.md §3. Importing every module here is also what registers their
domain-event handlers on the shared bus (§14), so the wiring is complete before the first
request is served.

Run:  uvicorn sincere.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sincere.shared import cache, db
from sincere.shared.config import get_settings
from sincere.shared.errors import register_error_handlers
from sincere.shared.logging import configure_logging
from sincere.shared.middleware import register_middleware

logger = logging.getLogger(__name__)


def _module_routers() -> list[tuple[object, str]]:
    """Import each module's router.

    Deferred to call time rather than module import so that a partially built module cannot
    break `import sincere.main` for the test suite. Each import also triggers the module's
    ``events.py`` handler registration (§14).
    """
    routers: list[tuple[object, str]] = []

    def add(import_path: str, label: str) -> None:
        # Importing `<module>.events` is what registers the module's domain-event handlers
        # on the shared bus (§14). It must happen even for a module with no HTTP surface,
        # so it is done first and independently of the router import.
        try:
            __import__(f"sincere.{label}.events")
        except ImportError:
            logger.debug("module.no_event_handlers", extra={"sincere_module": label})

        try:
            module = __import__(import_path, fromlist=["router"])
        except ImportError:
            logger.info("module.not_yet_implemented", extra={"sincere_module": label})
            return
        router = getattr(module, "router", None)
        if router is not None:
            routers.append((router, label))

    # Order matches §3's module table.
    add("sincere.identity.routes", "identity")
    add("sincere.admission.routes", "admission")
    add("sincere.matching.routes", "matching")
    add("sincere.chat.routes", "chat")
    add("sincere.antiabuse.routes", "antiabuse")
    add("sincere.monetization.routes", "monetization")
    add("sincere.feedback_ml.routes", "feedback_ml")
    add("sincere.admin.routes", "admin")
    return routers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    logger.info("app.starting", extra={"environment": settings.environment})

    await db.connect()
    await db.create_indexes()

    # §9 duplicate detection (FR-1.4) needs Atlas Vector Search. Report its availability at
    # boot rather than at first signup, so a misconfigured cluster surfaces immediately.
    vector_ready = await db.create_vector_index()
    app.state.vector_search_available = vector_ready

    await cache.connect()

    if settings.biometric_pipeline_enabled:
        logger.warning(
            "biometric.pipeline_enabled — §9:484 requires completed legal review of "
            "biometric consent language before this runs against real users."
        )
    else:
        logger.info(
            "biometric.pipeline_disabled — signups route to human review; "
            "set BIOMETRIC_PIPELINE_ENABLED=true only after legal sign-off (§9:484)."
        )

    logger.info("app.ready")
    yield

    logger.info("app.stopping")
    await cache.disconnect()
    await db.disconnect()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Sincère API",
        version="0.1.0",
        description=(
            "Verified-identity, ratio-balanced dating platform. "
            "Routes follow TECHNICAL_IMPLEMENTATION_PLAN.md §7 (API Design)."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
    )

    register_middleware(app)
    register_error_handlers(app)

    if settings.environment != "production":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    for router, label in _module_routers():
        app.include_router(router, prefix=settings.api_prefix)
        logger.debug("module.mounted", extra={"sincere_module": label})

    if settings.environment != "production" and not settings.object_storage_bucket:
        # Dev-only: accepts the uploads that LocalBackend's stand-in "pre-signed" URLs point
        # at. In production the bucket is configured, the S3 backend issues real pre-signed
        # URLs, and these routes do not exist at all.
        from sincere.shared.dev_routes import router as dev_storage_router

        app.include_router(dev_storage_router, prefix=settings.api_prefix)
        logger.warning(
            "dev_storage.mounted — object storage is unconfigured, so uploads are served by "
            "the API from local disk. Set OBJECT_STORAGE_BUCKET before any real deployment."
        )

    @app.get("/health", tags=["ops"], summary="Liveness and dependency health")
    async def health() -> dict[str, object]:
        """§21 health check. Reports dependency status without failing the probe on a
        degraded-but-serving dependency."""
        checks: dict[str, object] = {}
        try:
            await db.get_database().command("ping")
            checks["mongodb"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["mongodb"] = f"error: {exc}"
        try:
            await cache.get_redis().ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc}"

        checks["vector_search"] = (
            "ok" if getattr(app.state, "vector_search_available", False) else "unavailable"
        )
        checks["biometric_pipeline"] = (
            "enabled" if get_settings().biometric_pipeline_enabled else "disabled (legal gate)"
        )

        healthy = checks["mongodb"] == "ok" and checks["redis"] == "ok"
        return {"status": "ok" if healthy else "degraded", "checks": checks}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Prometheus scrape endpoint (§21)."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
