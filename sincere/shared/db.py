"""MongoDB access — cross-cutting plumbing only, no business logic.

Owns the Motor client, the canonical collection-name registry, and index bootstrap.

Two rules from TECHNICAL_IMPLEMENTATION_PLAN.md §3 that this module exists to support:

* Rule 1 — "a module's MongoDB collections are written **only** by that module". The
  ``COLLECTION_OWNER`` map below records that ownership so it is reviewable in one place,
  and :func:`collection` asserts it in dev/test.
* Index definitions live here rather than in each module's repository because the boot-time
  bootstrap must be a single idempotent pass (§15: jobs and startup must be safe to re-run).
"""

from __future__ import annotations

import logging
from typing import Any, Final

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from pymongo import ASCENDING, DESCENDING, GEOSPHERE, IndexModel
from pymongo.errors import OperationFailure

from sincere.shared.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Collection registry (§8)
# ---------------------------------------------------------------------------

class C:
    """Canonical collection names. Never hard-code a collection string elsewhere."""

    # --- Documented in §8 Database Schema ---
    USERS: Final = "users"
    EMBEDDINGS: Final = "embeddings"
    VERIFICATION_CAPTURES: Final = "verification_captures"
    SWIPES: Final = "swipes"
    MATCHES: Final = "matches"
    MESSAGES: Final = "messages"
    QUEUES: Final = "queues"
    SUBSCRIPTIONS: Final = "subscriptions"
    BOT_RISK_FLAGS: Final = "bot_risk_flags"
    WE_MET_RESPONSES: Final = "we_met_responses"
    DEVICE_SIGNALS: Final = "device_signals"
    INVOICES: Final = "invoices"

    # --- Operational collections implied by the doc but not enumerated in §8 ---
    DAILY_BATCHES: Final = "daily_batches"          # §11 step 7: the precomputed daily 15
    OUTBOX: Final = "outbox"                        # §14: at-least-once event delivery
    AUDIT_LOG: Final = "audit_log"                  # §22: append-only, separate store
    OTP_CHALLENGES: Final = "otp_challenges"        # §5: phone-OTP signup
    REFRESH_TOKENS: Final = "refresh_tokens"        # §5: rotation + reuse detection
    IDEMPOTENCY_KEYS: Final = "idempotency_keys"    # §7:391: payment and bid endpoints
    CONFIG_THRESHOLDS: Final = "config_thresholds"  # §2: tunable without redeploy
    PAYMENTS: Final = "payments"                    # §5 monetization: aggregator order records
    AUCTIONS: Final = "auctions"                    # §15a: settled daily auction records


#: §3 rule 1 — which module may *write* each collection. Reads by other modules must go
#: through the owning module's ``api.py``, never through a raw collection handle.
COLLECTION_OWNER: Final[dict[str, str]] = {
    C.USERS: "identity",
    C.EMBEDDINGS: "identity",
    C.VERIFICATION_CAPTURES: "identity",
    C.BOT_RISK_FLAGS: "identity",
    C.OTP_CHALLENGES: "identity",
    C.REFRESH_TOKENS: "identity",
    C.QUEUES: "admission",
    C.AUCTIONS: "admission",
    C.SWIPES: "matching",
    C.MATCHES: "matching",
    C.DAILY_BATCHES: "matching",
    C.MESSAGES: "chat",
    C.DEVICE_SIGNALS: "antiabuse",
    C.SUBSCRIPTIONS: "monetization",
    C.INVOICES: "monetization",
    C.PAYMENTS: "monetization",
    C.WE_MET_RESPONSES: "feedback_ml",
    C.CONFIG_THRESHOLDS: "admin",
    # shared infrastructure — written by shared/, not by any domain module
    C.OUTBOX: "shared",
    C.AUDIT_LOG: "shared",
    C.IDEMPOTENCY_KEYS: "shared",
}


# ---------------------------------------------------------------------------
# Index definitions (§8 "Key indexes")
# ---------------------------------------------------------------------------

def _seconds(days: int) -> int:
    return days * 24 * 60 * 60


INDEXES: Final[dict[str, list[IndexModel]]] = {
    C.USERS: [
        IndexModel([("phone_hash", ASCENDING)], unique=True, name="phone_hash_unique"),
        IndexModel([("status", ASCENDING)], name="status"),
        # §8: powers radius filtering for the candidate pool ($geoNear, §11 step 1)
        IndexModel([("last_recorded_location", GEOSPHERE)], name="location_2dsphere"),
        # §8: the ratio-count index — every hysteresis decision reads through this
        IndexModel(
            [
                ("h3_region", ASCENDING),
                ("gender", ASCENDING),
                ("activity.is_active_30d", ASCENDING),
            ],
            name="ratio_counts",
        ),
        IndexModel([("activity.last_login_at", DESCENDING)], name="last_login"),
        IndexModel([("activity.last_swipe_at", DESCENDING)], name="last_swipe"),
        # Retention cleanup job scans this (§15b) — sparse, most users have no value
        IndexModel([("hard_delete_after", ASCENDING)], sparse=True, name="hard_delete_after"),
    ],
    C.EMBEDDINGS: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("purpose", ASCENDING)], name="purpose"),
    ],
    C.VERIFICATION_CAPTURES: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("hard_delete_after", ASCENDING)], name="hard_delete_after"),
    ],
    C.SWIPES: [
        # §8: graduation counting + anti-spam rolling window
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_recent"),
        IndexModel([("target_id", ASCENDING)], name="target_id"),
        # Pool exclusion ("not already swiped", §11 step 1) needs the pair lookup
        IndexModel(
            [("user_id", ASCENDING), ("target_id", ASCENDING)],
            unique=True,
            name="user_target_unique",
        ),
    ],
    C.MATCHES: [
        IndexModel([("users", ASCENDING)], name="users"),
        IndexModel([("status", ASCENDING)], name="status"),
        IndexModel([("region", ASCENDING)], name="region"),
        IndexModel(
            [("messages_purge_after", ASCENDING)], sparse=True, name="messages_purge_after"
        ),
        IndexModel([("wemet.next_reask_at", ASCENDING)], sparse=True, name="wemet_reask"),
    ],
    C.MESSAGES: [
        # §8: chat history reads and ?after= delta sync
        IndexModel([("match_id", ASCENDING), ("sent_at", ASCENDING)], name="match_timeline"),
        IndexModel([("sender_id", ASCENDING)], name="sender_id"),
    ],
    C.QUEUES: [
        # _id IS the h3 cell (§8), so no extra index is needed for lookup by region
        IndexModel([("admission_state", ASCENDING)], name="admission_state"),
    ],
    C.SUBSCRIPTIONS: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("status", ASCENDING), ("renews_at", ASCENDING)], name="renewal_scan"),
    ],
    C.BOT_RISK_FLAGS: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        # The admin review queue reads exactly this (§7 GET /admin/review-queue)
        IndexModel([("band", ASCENDING), ("review.decided_at", ASCENDING)], name="review_queue"),
    ],
    C.WE_MET_RESPONSES: [
        IndexModel([("match_id", ASCENDING)], name="match_id"),
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("responded_at", DESCENDING)], name="responded_at"),
    ],
    C.DEVICE_SIGNALS: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("fingerprint", ASCENDING)], name="fingerprint"),
        IndexModel([("ip", ASCENDING)], name="ip"),
        # §8/§18 (DECIDED): 90-day rolling window, enforced by TTL rather than a job
        IndexModel(
            [("created_at", ASCENDING)],
            expireAfterSeconds=_seconds(90),
            name="ttl_90d",
        ),
    ],
    C.INVOICES: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("created_at", DESCENDING)], name="created_at"),
        # No TTL: §18 keeps payment records 5-7 years, decoupled from account deletion
    ],
    C.DAILY_BATCHES: [
        IndexModel(
            [("user_id", ASCENDING), ("batch_date", DESCENDING)],
            unique=True,
            name="user_date_unique",
        ),
        IndexModel([("region", ASCENDING), ("batch_date", DESCENDING)], name="region_date"),
    ],
    C.OUTBOX: [
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="dispatch_scan"),
        IndexModel([("event_name", ASCENDING)], name="event_name"),
    ],
    C.AUDIT_LOG: [
        IndexModel([("at", DESCENDING)], name="at"),
        IndexModel([("actor_id", ASCENDING)], name="actor_id"),
        IndexModel([("action", ASCENDING), ("at", DESCENDING)], name="action_at"),
        # Deliberately NO TTL — §22 keeps audit logs long-lived; app logs expire elsewhere
    ],
    C.OTP_CHALLENGES: [
        IndexModel([("phone_hash", ASCENDING)], name="phone_hash"),
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_expiry"),
    ],
    C.REFRESH_TOKENS: [
        IndexModel([("token_hash", ASCENDING)], unique=True, name="token_hash_unique"),
        # §5: reuse detection revokes the whole family, so the family is the lookup key
        IndexModel([("family_id", ASCENDING)], name="family_id"),
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_expiry"),
    ],
    C.IDEMPOTENCY_KEYS: [
        IndexModel(
            [("key", ASCENDING), ("endpoint", ASCENDING)], unique=True, name="key_endpoint_unique"
        ),
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_expiry"),
    ],
    C.CONFIG_THRESHOLDS: [
        IndexModel([("applied_at", DESCENDING)], name="applied_at"),
    ],
    C.PAYMENTS: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        IndexModel([("aggregator_ref", ASCENDING)], unique=True, sparse=True, name="agg_ref"),
        IndexModel([("status", ASCENDING)], name="status"),
    ],
    C.AUCTIONS: [
        IndexModel(
            [("region", ASCENDING), ("window_end", DESCENDING)], unique=True, name="region_window"
        ),
        IndexModel([("status", ASCENDING)], name="status"),
    ],
}


#: Atlas Vector Search index for duplicate detection (§9). Cosine similarity ONLY —
#: the embedding is never decomposed into named facial features (§9 legal posture).
VECTOR_INDEX_NAME: Final = "embedding_vector_index"


def vector_index_definition(dimensions: int) -> dict[str, Any]:
    return {
        "fields": [
            {
                "type": "vector",
                "path": "vector",
                "numDimensions": dimensions,
                "similarity": "cosine",
            },
            # Filter field so a duplicate search can exclude the user's own vector
            {"type": "filter", "path": "user_id"},
        ]
    }


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect() -> AsyncIOMotorDatabase:
    """Open the Motor client and return the application database."""
    global _client, _database
    if _database is not None:
        return _database

    settings = get_settings()
    _client = AsyncIOMotorClient(
        settings.mongodb_uri,
        uuidRepresentation="standard",
        tz_aware=True,
        serverSelectionTimeoutMS=10_000,
    )
    _database = _client[settings.mongodb_database]
    await _client.admin.command("ping")
    logger.info("mongodb.connected", extra={"database": settings.mongodb_database})
    return _database


async def disconnect() -> None:
    global _client, _database
    if _client is not None:
        _client.close()
    _client, _database = None, None


def get_database() -> AsyncIOMotorDatabase:
    """Return the connected database. Raises if :func:`connect` has not run."""
    if _database is None:
        raise RuntimeError("Database not connected — call sincere.shared.db.connect() first")
    return _database


def collection(name: str) -> AsyncIOMotorCollection:
    """Return a collection handle by canonical name."""
    return get_database()[name]


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

async def create_indexes(db: AsyncIOMotorDatabase | None = None) -> None:
    """Create every §8 index. Idempotent — safe on every boot."""
    # Motor Database objects raise on truth testing (to catch `if collection:` bugs),
    # so this must be an explicit None check rather than `db or get_database()`.
    db = get_database() if db is None else db
    for name, models in INDEXES.items():
        if not models:
            continue
        try:
            await db[name].create_indexes(models)
        except OperationFailure as exc:
            # An index that exists with different options is a migration concern, not a
            # startup failure — surface it loudly but let the app come up.
            logger.error("index.create_failed", extra={"collection": name, "error": str(exc)})
    logger.info("mongodb.indexes_ready", extra={"collections": len(INDEXES)})


async def create_vector_index(db: AsyncIOMotorDatabase | None = None) -> bool:
    """Create the Atlas Vector Search index on ``embeddings.vector`` (§9).

    Returns ``True`` if the index exists or was created, ``False`` if the deployment does
    not support Atlas Search. Duplicate detection (FR-1.4) is unavailable in the latter
    case; the caller decides whether that is fatal.
    """
    # Motor Database objects raise on truth testing (to catch `if collection:` bugs),
    # so this must be an explicit None check rather than `db or get_database()`.
    db = get_database() if db is None else db
    settings = get_settings()
    coll = db[C.EMBEDDINGS]

    try:
        existing = await coll.list_search_indexes().to_list(length=None)
        if any(index.get("name") == VECTOR_INDEX_NAME for index in existing):
            logger.info("atlas.vector_index_present", extra={"index_name": VECTOR_INDEX_NAME})
            return True

        from pymongo.operations import SearchIndexModel

        await coll.create_search_index(
            SearchIndexModel(
                definition=vector_index_definition(settings.embedding_dimensions),
                name=VECTOR_INDEX_NAME,
                type="vectorSearch",
            )
        )
        logger.info("atlas.vector_index_created", extra={"index_name": VECTOR_INDEX_NAME})
        return True
    except OperationFailure as exc:
        logger.warning(
            "atlas.vector_index_unavailable — duplicate detection (FR-1.4) will not run. "
            "Atlas Vector Search requires an M10+ cluster; the free M0 tier does not support it.",
            extra={"error": str(exc)},
        )
        return False
