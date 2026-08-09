"""We-Met loop and model retraining (FR-4.3-4.4, §13).

FR-4.3 (DECIDED): the prompt fires at **20-30 total messages within a 3-day window** (no
per-day minimum), and re-fires **every 1-2 weeks** on "not yet met" until met or unmatched.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sincere.chat import api as chat
from sincere.feedback_ml import repository as repo
from sincere.feedback_ml.schemas import (
    PendingPromptsResponse,
    SubmitResponseResponse,
    WeMetPrompt,
    WeMetResponse,
)
from sincere.identity import api as identity
from sincere.matching import api as matching
from sincere.shared.config import get_settings
from sincere.shared.errors import ConflictError, ForbiddenError, NotFoundError
from sincere.shared.events import Event, bus
from sincere.shared.threshold_store import load as load_thresholds

logger = logging.getLogger(__name__)

QUESTION = "Have you two met in person yet?"
REASK_QUESTION = "Checking back in — have you met in person yet?"


# ---------------------------------------------------------------------------
# FR-4.3 trigger
# ---------------------------------------------------------------------------

async def check_trigger(match_id: str) -> bool:
    """Should this match fire a We-Met prompt now?

    FR-4.3's window is the subtle part: **20-30 messages within a 3-day window**, counted as
    total messages in the window rather than per day. Two people who exchange 25 messages in
    one evening qualify; two who exchange 25 over a month do not, because that is not the
    conversational intensity that precedes meeting.
    """
    settings = get_settings()
    if not settings.wemet_enabled:
        return False

    thresholds = await load_thresholds()
    match = await matching.get_match(match_id)
    if match is None or match.get("status") != "active":
        return False

    wemet = match.get("wemet") or {}
    if wemet.get("triggered_at"):
        return False  # already prompted; re-asks go through the scheduler

    since = datetime.now(UTC) - timedelta(days=thresholds.wemet_trigger_window_days)
    in_window = await chat.messages_in_window(match_id, since)

    return in_window >= thresholds.wemet_trigger_messages


async def fire_prompt(match_id: str) -> None:
    """Mark a match as prompted and announce it (§14 ``WeMetThresholdReached``)."""
    now = datetime.now(UTC)
    await repo.set_prompt_state(match_id, triggered_at=now, next_reask_at=None)

    await bus.emit(Event.WEMET_THRESHOLD_REACHED, {"match_id": match_id, "at": now.isoformat()})
    logger.info("wemet.prompt_fired", extra={"match_id": match_id})


async def pending_prompts(user_id: str) -> PendingPromptsResponse:
    """``GET /wemet/pending``."""
    thresholds = await load_thresholds()
    matches = await repo.pending_for_user(user_id)

    prompts: list[WeMetPrompt] = []
    for match in matches:
        wemet = match.get("wemet") or {}
        triggered_at = wemet.get("triggered_at")
        if not triggered_at:
            continue

        # A re-ask opens a fresh round, so "already answered" is scoped to the current round.
        round_start = triggered_at
        if await repo.already_responded(match["_id"], user_id, round_start):
            continue

        other_id = next((uid for uid in match["users"] if uid != user_id), None)
        if other_id is None:
            continue
        card = await identity.get_profile_card(other_id)
        reask_number = len(wemet.get("responses") or [])

        prompts.append(
            WeMetPrompt(
                prompt_id=match["_id"],
                match_id=match["_id"],
                other_user_id=other_id,
                other_name=(card or {}).get("name"),
                triggered_at=triggered_at,
                question=REASK_QUESTION if reask_number else QUESTION,
                reask_number=reask_number,
            )
        )

    logger.debug(
        "wemet.pending",
        extra={
            "user_id": user_id,
            "count": len(prompts),
            "window_days": thresholds.wemet_trigger_window_days,
        },
    )
    return PendingPromptsResponse(prompts=prompts)


async def submit_response(
    prompt_id: str, user_id: str, response: WeMetResponse, note: str | None
) -> SubmitResponseResponse:
    """``POST /wemet/:promptId/response``.

    FR-4.3: ``met_no_yet`` schedules a re-ask in 1-2 weeks. The other two answers are
    terminal — continuing to ask someone who said "not going to" would be harassment by
    scheduler.
    """
    match = await matching.get_match(prompt_id)
    if match is None:
        raise NotFoundError("Prompt")
    if user_id not in match.get("users", []):
        raise ForbiddenError("Not your prompt", "This prompt belongs to a different match.")

    wemet = match.get("wemet") or {}
    triggered_at = wemet.get("triggered_at")
    if not triggered_at:
        raise ConflictError("No prompt pending", "There is no We-Met question to answer here.")

    if await repo.already_responded(prompt_id, user_id, triggered_at):
        raise ConflictError("Already answered", "You have already answered this question.")

    await repo.record_response(
        match_id=prompt_id, user_id=user_id, response=str(response), note=note
    )
    await repo.append_response_to_match(
        prompt_id,
        {"user_id": user_id, "response": str(response), "at": datetime.now(UTC)},
    )

    next_reask_at: datetime | None = None
    if response is WeMetResponse.MET_NO_YET:
        next_reask_at = await _schedule_reask()
        await repo.set_prompt_state(prompt_id, triggered_at=None, next_reask_at=next_reask_at)
        message = "Thanks — we will check back in a couple of weeks."
    else:
        # Terminal for this match: stop asking entirely.
        await repo.set_prompt_state(prompt_id, triggered_at=None, next_reask_at=None)
        message = (
            "Thank you — this genuinely improves who we show you."
            if response is WeMetResponse.MET_YES
            else "Thanks for letting us know."
        )

    logger.info(
        "wemet.response_recorded", extra={"match_id": prompt_id, "response": str(response)}
    )
    return SubmitResponseResponse(
        prompt_id=prompt_id, recorded=True, next_reask_at=next_reask_at, message=message
    )


async def _schedule_reask() -> datetime:
    """FR-4.3: re-fire "every 1-2 weeks".

    Jittered across the range rather than fixed at 7 or 14 days, so re-asks spread out instead
    of arriving as a weekly batch to everyone who answered on the same day.
    """
    thresholds = await load_thresholds()
    span = max(0, thresholds.wemet_reask_days_max - thresholds.wemet_reask_days_min)
    days = thresholds.wemet_reask_days_min + (secrets.randbelow(span + 1) if span else 0)
    return datetime.now(UTC) + timedelta(days=days)


async def run_scheduler() -> dict[str, int]:
    """The §15b We-Met scheduler: fire new prompts, and re-fire due ones (FR-4.3)."""
    settings = get_settings()
    if not settings.wemet_enabled:
        return {"fired": 0, "reasked": 0, "skipped": 1}

    fired = 0
    for match in await repo.untriggered_active_matches():
        if await check_trigger(match["_id"]):
            await fire_prompt(match["_id"])
            fired += 1

    reasked = 0
    now = datetime.now(UTC)
    for match in await repo.matches_due_for_prompt(now):
        await repo.set_prompt_state(match["_id"], triggered_at=now, next_reask_at=None)
        reasked += 1

    logger.info("wemet.scheduler_run", extra={"fired": fired, "reasked": reasked})
    return {"fired": fired, "reasked": reasked}


# ---------------------------------------------------------------------------
# §13 retraining
# ---------------------------------------------------------------------------

async def retrain() -> dict[str, Any]:
    """Assemble the training set, train, gate on holdout, promote or keep (§13).

    The gate is the whole point: §13's diagram routes a failed holdout to "Keep current
    model", and this returns without touching the registry in that case.
    """
    from sincere.feedback_ml import training
    from sincere.matching import models

    rows = await repo.training_rows()
    if len(rows) < training.MIN_TRAINING_ROWS:
        logger.info(
            "training.insufficient_labels",
            extra={"rows": len(rows), "required": training.MIN_TRAINING_ROWS},
        )
        return {
            "trained": False,
            "promoted": False,
            "reason": (
                f"only {len(rows)} labelled rows; need {training.MIN_TRAINING_ROWS}. "
                "The cold-start priors remain in use (§10:507)."
            ),
            "rows": len(rows),
        }

    train_rows, holdout_rows = training.split_holdout(rows)
    trained = training.train_reciprocity(train_rows)
    if trained is None:
        return {
            "trained": False,
            "promoted": False,
            "reason": "XGBoost unavailable; install requirements-ml.txt",
            "rows": len(rows),
        }

    booster, feature_order = trained
    predictions = training.predict_batch(booster, feature_order, holdout_rows)
    candidate_auc = training.auc(predictions, [r["label"] for r in holdout_rows])

    incumbent = models.read_registry()
    incumbent_auc = incumbent.get("holdout_auc")

    promote, reason = training.passes_holdout_gate(candidate_auc, incumbent_auc)
    if not promote:
        logger.warning("training.holdout_gate_failed", extra={"reason": reason})
        return {
            "trained": True,
            "promoted": False,
            "reason": reason,
            "rows": len(rows),
            "holdout_auc": candidate_auc,
        }

    version = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    registry = models.registry_path()
    registry.mkdir(parents=True, exist_ok=True)
    model_file = f"reciprocity_{version}.json"
    booster.save_model(str(registry / model_file))

    models.promote(
        {
            "version": version,
            "reciprocity": {"file": model_file, "features": feature_order},
            "holdout_auc": candidate_auc,
            "training_rows": len(rows),
            "promoted_at": datetime.now(UTC).isoformat(),
        }
    )
    models.reset_cache()

    logger.info(
        "training.promoted",
        extra={"version": version, "holdout_auc": candidate_auc, "rows": len(rows)},
    )
    return {
        "trained": True,
        "promoted": True,
        "reason": reason,
        "rows": len(rows),
        "holdout_auc": candidate_auc,
        "version": version,
    }
