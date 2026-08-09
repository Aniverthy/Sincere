"""HTTP routes for antiabuse.

§7 does not enumerate anti-abuse endpoints — the module is mostly event-driven. What the
client genuinely needs is the warning interstitial (§4: "Renders anti-abuse warning
interstitials (1st/2nd/3rd occasion) distinctly from ban notice") and a way to acknowledge it.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from sincere.antiabuse import service
from sincere.shared.auth import PROFILE_SCOPES, Principal, require_scopes

router = APIRouter(tags=["antiabuse"])

AnyPrincipal = Annotated[Principal, Depends(require_scopes(*PROFILE_SCOPES))]


@router.get("/warnings/pending", summary="Unacknowledged warning interstitial, if any")
async def pending(principal: AnyPrincipal) -> dict[str, Any]:
    warning = await service.pending_warning(principal.user_id)
    return {"warning": warning}


@router.post("/warnings/acknowledge", summary="Mark the current warning as seen")
async def acknowledge(principal: AnyPrincipal) -> dict[str, str]:
    await service.acknowledge_warning(principal.user_id)
    return {"status": "acknowledged"}
