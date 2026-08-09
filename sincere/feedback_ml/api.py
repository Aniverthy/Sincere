"""Public interface of the feedback_ml module (§3 rule 2)."""

from __future__ import annotations

from typing import Any

from sincere.feedback_ml import repository as _repo
from sincere.feedback_ml import service as _service


async def check_trigger(match_id: str) -> bool:
    """FR-4.3: has this conversation reached the We-Met threshold?"""
    return await _service.check_trigger(match_id)


async def fire_prompt(match_id: str) -> None:
    await _service.fire_prompt(match_id)


async def run_scheduler() -> dict[str, int]:
    """§15b We-Met scheduler: fire new prompts and re-fire due ones."""
    return await _service.run_scheduler()


async def retrain() -> dict[str, Any]:
    """§13 batch retrain with holdout gating."""
    return await _service.retrain()


async def label_count() -> int:
    """How many We-Met labels exist. §25 phase 3 gates on this volume being meaningful."""
    return await _repo.label_count()


async def responses_for_match(match_id: str) -> list[dict[str, Any]]:
    return await _repo.responses_for_match(match_id)


async def model_info() -> dict[str, Any]:
    """Current registry entry, for the FR-8.1 admin dashboard."""
    from sincere.matching import models

    registry = models.read_registry()
    reciprocity, collaborative = models.get_providers()
    return {
        "version": registry.get("version", "cold-start"),
        "reciprocity_model": reciprocity.name,
        "collaborative_model": collaborative.name,
        "promoted_at": registry.get("promoted_at"),
        "holdout_auc": registry.get("holdout_auc"),
        "training_rows": registry.get("training_rows", 0),
    }


__all__ = [
    "check_trigger",
    "fire_prompt",
    "label_count",
    "model_info",
    "responses_for_match",
    "retrain",
    "run_scheduler",
]
