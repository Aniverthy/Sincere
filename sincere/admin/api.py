"""Public interface of the admin module.

Deliberately minimal. §3 makes admin a **consumer**: it reads other modules' ``api.py`` and is
imported by none of them — the import-linter contract "admin is a consumer" enforces that.
This file exists for the ops tooling and tests, not for other domain modules.
"""

from __future__ import annotations

from typing import Any

from sincere.admin import service as _service


async def system_health() -> dict[str, Any]:
    """The §21 business-health metrics in one view."""
    return (await _service.system_health()).model_dump(mode="json")


async def regions() -> dict[str, Any]:
    return (await _service.regions()).model_dump(mode="json")


async def review_queue(limit: int = 50) -> dict[str, Any]:
    return (await _service.review_queue(limit)).model_dump(mode="json")


__all__ = ["regions", "review_queue", "system_health"]
