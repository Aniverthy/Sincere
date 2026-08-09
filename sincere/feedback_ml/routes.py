"""HTTP routes for feedback_ml (§7 We Met)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from sincere.feedback_ml import service
from sincere.feedback_ml.schemas import (
    PendingPromptsResponse,
    SubmitResponseRequest,
    SubmitResponseResponse,
)
from sincere.shared.auth import CHAT_SCOPES, Principal, require_scopes

router = APIRouter(tags=["feedback_ml"])

ActivePrincipal = Annotated[Principal, Depends(require_scopes(*CHAT_SCOPES))]


@router.get(
    "/wemet/pending",
    response_model=PendingPromptsResponse,
    summary="Prompts awaiting an answer",
)
async def pending(principal: ActivePrincipal) -> PendingPromptsResponse:
    return await service.pending_prompts(principal.user_id)


@router.post(
    "/wemet/{prompt_id}/response",
    response_model=SubmitResponseResponse,
    summary="met_yes / met_no_yet / not_going_to — met_no_yet re-asks in 1-2 weeks",
)
async def respond(
    prompt_id: str, payload: SubmitResponseRequest, principal: ActivePrincipal
) -> SubmitResponseResponse:
    return await service.submit_response(
        prompt_id, principal.user_id, payload.response, payload.note
    )
