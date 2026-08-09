"""Runtime threshold overrides — cross-cutting plumbing only, no business logic.

TECHNICAL_IMPLEMENTATION_PLAN.md §2 (Configurability): "All launch-default thresholds
(hysteresis band, dwell rules, similarity cutoffs, weights) tunable via config **without
redeploy**" — because the decision record explicitly flags them for post-launch refinement.
§23:809 restates it: "Config/threshold changes deploy via audited admin config, not code releases."

Resolution order for any threshold:

1. an override stored in ``config_thresholds`` by the admin API, else
2. the launch default from :class:`sincere.shared.config.Thresholds`.

Reads go through a short-TTL Redis cache so an admin change propagates across every API
replica within a minute without any restart or pub/sub machinery.

Writes belong to the admin module (§7 ``PATCH /admin/config/thresholds``); this module only
provides the persistence and the validated apply. Every write is audited with actor and
before/after (§18).
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from sincere.shared import cache
from sincere.shared.audit import AuditAction, record
from sincere.shared.config import Thresholds, get_default_thresholds
from sincere.shared.db import C, collection
from sincere.shared.errors import ValidationError

logger = logging.getLogger(__name__)

#: Thresholds that may never be changed at runtime, with the reason.
IMMUTABLE: dict[str, str] = {
    "weight_final_visual": (
        "FR-3.6 fixes the visual-pattern weight at 0.05 by decision record — not tunable"
    ),
    "h3_resolution": (
        "Changing H3 resolution re-partitions every region and invalidates all queue state; "
        "it is a migration, not a config change (FR-2.1)"
    ),
}

_DOC_ID = "current"


async def load() -> Thresholds:
    """Return the effective thresholds: stored overrides layered over launch defaults."""
    cached = await _cached_overrides()
    defaults = get_default_thresholds()
    if not cached:
        return defaults
    return Thresholds(**{**defaults.model_dump(), **cached})


async def _cached_overrides() -> dict[str, Any]:
    key = cache.Keys.thresholds()
    try:
        hit = await cache.get_json(key)
        if hit is not None:
            return hit
    except Exception:  # noqa: BLE001
        logger.debug("thresholds.cache_unavailable")

    doc = await collection(C.CONFIG_THRESHOLDS).find_one({"_id": _DOC_ID})
    overrides = (doc or {}).get("overrides", {})
    with contextlib.suppress(Exception):
        await cache.set_json(key, overrides, ttl=cache.TTL["thresholds"])
    return overrides


async def apply(
    changes: dict[str, Any], *, actor_id: str, reason: str | None = None
) -> Thresholds:
    """Validate and persist threshold overrides. Returns the new effective thresholds.

    Validation runs the full :class:`Thresholds` model, so the §12 weight-sum invariants and
    the FR-2.4 hysteresis-band invariant reject a bad change *before* it reaches the database.
    A misconfigured band would make the admission state machine flap in production.
    """
    if not changes:
        raise ValidationError("No threshold changes supplied.")

    defaults = get_default_thresholds()
    unknown = set(changes) - set(defaults.model_fields)
    if unknown:
        raise ValidationError(f"Unknown threshold(s): {', '.join(sorted(unknown))}")

    blocked = set(changes) & set(IMMUTABLE)
    if blocked:
        raise ValidationError(
            "; ".join(f"{name}: {IMMUTABLE[name]}" for name in sorted(blocked))
        )

    before = await load()
    candidate = {**before.model_dump(), **changes}
    try:
        after = Thresholds(**candidate)
    except PydanticValidationError as exc:
        raise ValidationError(
            "The requested thresholds violate a documented invariant.",
            [
                {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ],
        ) from exc

    existing = await collection(C.CONFIG_THRESHOLDS).find_one({"_id": _DOC_ID}) or {}
    overrides = {**existing.get("overrides", {}), **changes}

    await collection(C.CONFIG_THRESHOLDS).update_one(
        {"_id": _DOC_ID},
        {
            "$set": {
                "overrides": overrides,
                "applied_at": datetime.now(UTC),
                "applied_by": actor_id,
                "reason": reason,
            }
        },
        upsert=True,
    )
    await cache.invalidate(cache.Keys.thresholds())

    # §18: threshold changes are logged with actor + before/after.
    await record(
        AuditAction.THRESHOLD_CHANGED,
        actor_id=actor_id,
        before={k: getattr(before, k) for k in changes},
        after={k: getattr(after, k) for k in changes},
        context={"reason": reason},
    )
    logger.info("thresholds.applied", extra={"fields": sorted(changes), "actor_id": actor_id})
    return after


async def reset(field: str, *, actor_id: str) -> Thresholds:
    """Drop one override, returning that threshold to its launch default."""
    before = await load()
    await collection(C.CONFIG_THRESHOLDS).update_one(
        {"_id": _DOC_ID}, {"$unset": {f"overrides.{field}": ""}}
    )
    await cache.invalidate(cache.Keys.thresholds())
    after = await load()
    await record(
        AuditAction.THRESHOLD_CHANGED,
        actor_id=actor_id,
        before={field: getattr(before, field, None)},
        after={field: getattr(after, field, None)},
        context={"reason": "reset to launch default"},
    )
    return after
