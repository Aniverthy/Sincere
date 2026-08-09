"""Request/response models for feedback_ml (§7 We Met)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class WeMetResponse(StrEnum):
    """FR-4.3's three answers.

    ``MET_NO_YET`` is the one that matters structurally: it schedules a re-ask in 1-2 weeks,
    whereas the other two are terminal for that match.
    """

    MET_YES = "met_yes"
    MET_NO_YET = "met_no_yet"
    NOT_GOING_TO = "not_going_to"


class WeMetPrompt(BaseModel):
    """``GET /wemet/pending``."""

    prompt_id: str
    match_id: str
    other_user_id: str
    other_name: str | None = None
    triggered_at: datetime
    question: str
    reask_number: int = 0


class PendingPromptsResponse(BaseModel):
    prompts: list[WeMetPrompt]


class SubmitResponseRequest(BaseModel):
    """``POST /wemet/:promptId/response``."""

    response: WeMetResponse
    note: str | None = Field(default=None, max_length=500)


class SubmitResponseResponse(BaseModel):
    prompt_id: str
    recorded: bool
    next_reask_at: datetime | None = None
    message: str


class ModelVersionInfo(BaseModel):
    """§13 registry entry, surfaced to the admin dashboard."""

    version: str
    reciprocity_model: str
    collaborative_model: str
    promoted_at: datetime | None = None
    holdout_auc: float | None = None
    training_rows: int = 0
