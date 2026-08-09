"""Face-embedding pipeline (TECHNICAL_IMPLEMENTATION_PLAN.md §9).

One embedding pipeline, **two sanctioned uses**: duplicate detection and personalized
visual-pattern matching. Nothing else — explicitly never marketing.

Constraints carried verbatim from §9, each enforced by code below rather than by convention:

* **Cosine similarity only.** No function here extracts, names, or returns a facial attribute.
  The legal posture depends on "similarity-only embeddings" not being "facial geometry".
* **FaceNet via DeepFace**, chosen for clean commercial licensing; swappable through DeepFace's
  config string if InsightFace is ever licensed.
* **Data minimization.** The source image buffer is discarded immediately after the vector is
  produced; only the vector is persisted (§18).
* **Legal gate.** §9:484 makes combined legal review a hard blocker. With
  ``BIOMETRIC_PIPELINE_ENABLED=false`` the pipeline refuses to run and signups route to human
  review instead — a safe default, never a silent skip.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol

from sincere.shared.config import get_settings
from sincere.shared.db import VECTOR_INDEX_NAME, C, collection

logger = logging.getLogger(__name__)


class BiometricPipelineDisabled(RuntimeError):
    """Raised when the pipeline is invoked while the §9:484 legal gate is closed."""


@dataclass(slots=True, frozen=True)
class DuplicateHit:
    user_id: str
    similarity: float


class EmbeddingProvider(Protocol):
    """§9 keeps the backend swappable via DeepFace's config-string abstraction."""

    def embed(self, image_bytes: bytes) -> list[float]:  # pragma: no cover - interface
        ...


class DeepFaceProvider:
    """FaceNet embeddings via DeepFace (FR-1.3, DECIDED).

    Imported lazily: TensorFlow is a ~1GB dependency in ``requirements-ml.txt``, and the API
    must boot without it while the legal gate is closed.
    """

    def __init__(self, backend: str, dimensions: int) -> None:
        self._backend = backend
        self._dimensions = dimensions

    def embed(self, image_bytes: bytes) -> list[float]:
        import tempfile
        from pathlib import Path

        from deepface import DeepFace

        # DeepFace reads from a path. The temp file is deleted in the finally block, and the
        # caller discards `image_bytes` — §18's "image buffer discarded post-embedding".
        tmp = Path(tempfile.mkstemp(suffix=".jpg")[1])
        try:
            tmp.write_bytes(image_bytes)
            result = DeepFace.represent(
                img_path=str(tmp),
                model_name=self._backend,
                enforce_detection=True,
                detector_backend="opencv",
            )
            vector = result[0]["embedding"]
            if len(vector) != self._dimensions:
                logger.warning(
                    "biometric.unexpected_dimensions",
                    extra={"expected": self._dimensions, "actual": len(vector)},
                )
            return [float(v) for v in vector]
        finally:
            tmp.unlink(missing_ok=True)


_provider: EmbeddingProvider | None = None


def get_provider() -> EmbeddingProvider:
    global _provider
    settings = get_settings()
    if not settings.biometric_pipeline_enabled:
        raise BiometricPipelineDisabled(
            "The face pipeline is disabled. §9:484 requires completed legal review of "
            "biometric consent language before it may run. Set BIOMETRIC_PIPELINE_ENABLED=true "
            "only after legal sign-off."
        )
    if _provider is None:
        _provider = DeepFaceProvider(settings.embedding_backend, settings.embedding_dimensions)
    return _provider


def set_provider(provider: EmbeddingProvider | None) -> None:
    """Test seam. Production selects the provider through :func:`get_provider`."""
    global _provider
    _provider = provider


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity, normalized to 0-1.

    Raw cosine ranges -1..1; §12 declares every similarity variable to be 0-1, so the result
    is mapped rather than clamped — clamping would collapse all opposing vectors onto 0 and
    lose ordering information.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return (dot / (norm_a * norm_b) + 1.0) / 2.0


async def find_duplicates(
    vector: list[float], *, exclude_user_id: str, threshold: float, limit: int = 10
) -> list[DuplicateHit]:
    """FR-1.4 duplicate check against all existing embeddings.

    Uses Atlas ``$vectorSearch`` (§9). If the deployment has no Atlas Search index — a local
    community server, or an M0 cluster — this falls back to an exact scan so development and
    the test suite still exercise the real decision logic. The fallback is logged loudly
    because it is O(n) and unacceptable at production scale.

    Returns hits at or above ``threshold``. **The caller must route these to human review and
    never auto-ban** (FR-1.4, DECIDED).
    """
    try:
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX_NAME,
                    "path": "vector",
                    "queryVector": vector,
                    "numCandidates": max(limit * 20, 100),
                    "limit": limit,
                    "filter": {"user_id": {"$ne": exclude_user_id}},
                }
            },
            {"$project": {"user_id": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]
        cursor = collection(C.EMBEDDINGS).aggregate(pipeline)
        hits = [
            DuplicateHit(user_id=doc["user_id"], similarity=float(doc["score"]))
            async for doc in cursor
        ]
        return [hit for hit in hits if hit.similarity >= threshold]
    except Exception as exc:  # noqa: BLE001 — any Atlas Search absence lands here
        logger.warning(
            "biometric.vector_search_fallback — Atlas Vector Search unavailable, scanning "
            "embeddings exhaustively. This is O(n) and must not run in production (§9).",
            extra={"error": str(exc)},
        )
        return await _scan_for_duplicates(vector, exclude_user_id, threshold, limit)


async def _scan_for_duplicates(
    vector: list[float], exclude_user_id: str, threshold: float, limit: int
) -> list[DuplicateHit]:
    hits: list[DuplicateHit] = []
    cursor = collection(C.EMBEDDINGS).find({"user_id": {"$ne": exclude_user_id}})
    async for doc in cursor:
        similarity = cosine_similarity(vector, doc.get("vector", []))
        if similarity >= threshold:
            hits.append(DuplicateHit(user_id=doc["user_id"], similarity=similarity))
    hits.sort(key=lambda hit: hit.similarity, reverse=True)
    return hits[:limit]


def photo_matches_selfie(
    photo_vector: list[float], selfie_vector: list[float], floor: float
) -> bool:
    """FR-1.5: blocks the "verify a real face, then swap in stolen photos" scam.

    Returns whether the profile photo and the verification selfie are the same person, by
    cosine similarity alone.
    """
    return cosine_similarity(photo_vector, selfie_vector) >= floor


# ---------------------------------------------------------------------------
# Liveness prompts (FR-1.2)
# ---------------------------------------------------------------------------

#: §5: "randomized prompt sequence". Randomization is the defence — a recording of someone
#: else's session will not contain this sequence, so replay and static photos both fail.
LIVENESS_PROMPTS: tuple[str, ...] = (
    "blink_twice",
    "turn_head_left",
    "turn_head_right",
    "look_up",
    "smile",
    "open_mouth",
)


def random_prompt_sequence(length: int = 3) -> list[str]:
    import secrets

    pool = list(LIVENESS_PROMPTS)
    chosen: list[str] = []
    for _ in range(min(length, len(pool))):
        chosen.append(pool.pop(secrets.randbelow(len(pool))))
    return chosen
