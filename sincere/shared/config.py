"""Configuration — cross-cutting plumbing only, no business logic.

Two distinct layers, deliberately separated:

1. :class:`Settings` — *infrastructure* config read from the environment at process start.
   Connection strings, secrets, feature gates. Changing these requires a redeploy.

2. :class:`Thresholds` — *product* config: every launch default the decision record flagged
   for post-launch refinement. TECHNICAL_IMPLEMENTATION_PLAN.md §2 (Configurability) requires
   these be "tunable via config without redeploy", so they live in MongoDB, are cached in
   Redis, and are edited through the audited admin endpoint (§7 ``PATCH /admin/config/thresholds``).

The environment supplies the *initial* values for layer 2 (see ``.env.example``); once a
threshold has been overridden through the admin API, the stored value wins.
"""

from __future__ import annotations

import functools
from typing import Annotated, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Ratio = Annotated[float, Field(ge=0.0, le=1.0)]


class Settings(BaseSettings):
    """Infrastructure configuration. Read once at startup from environment/.env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    # --- Environment ---
    environment: Literal["dev", "test", "staging", "production"] = "dev"
    debug: bool = False
    api_prefix: str = "/v1"

    # --- Data stores ---
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "sincere"
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth (§5) ---
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl: int = 900  # 15 min — §5 "short-lived access JWT"
    jwt_refresh_ttl: int = 2_592_000  # 30 days — matches the activity-window definition
    jwt_issuer: str = "sincere"

    # --- Object storage (§4 pre-signed uploads) ---
    object_storage_bucket: str = ""
    object_storage_region: str = "ap-south-1"
    object_storage_endpoint: str | None = None  # S3-compatible; None = AWS
    object_storage_key: str = ""
    object_storage_secret: str = ""
    presigned_url_ttl: int = 900

    # --- Payments (§3: aggregator adapter, vendor TBD) ---
    payment_provider: Literal["sandbox", "razorpay"] = "sandbox"
    payment_aggregator_key: str = ""
    payment_aggregator_secret: str = ""
    payment_webhook_secret: str = ""

    # --- OTP delivery (§17: SMS is OTP-only, never marketing) ---
    sms_provider: Literal["console", "twilio"] = "console"
    sms_account_sid: str = ""
    sms_auth_token: str = ""
    sms_from_number: str = ""

    # --- Feature gates ---
    biometric_pipeline_enabled: bool = False
    """§9:484 — combined legal review of biometric consent is a HARD BLOCKER before the
    face pipeline may ship. Defaults off; enabling it in production is a deliberate act.
    With this off, signup routes to human review instead of running embeddings."""

    dev_auto_approve_verification: bool = False
    """Skip the human review queue during development.

    With ``biometric_pipeline_enabled`` false (the §9:484 legal gate), every signup correctly
    routes to human review — which makes the app untestable end-to-end without an operator
    approving each account by hand.

    This flag short-circuits that **in development only**. The validator below refuses to let
    it load in production, so it cannot become an accidental route around FR-1.6: a real
    deployment either runs the biometric pipeline or queues for a human, never neither.
    """

    wemet_enabled: bool = True
    """FR-4.3 — We-Met rolls out shortly post-MVP. Built now, gated for launch timing."""

    push_notifications_enabled: bool = False
    """§17 — push is DECIDED-deferred to v2. The notification module is event-consuming
    from day one so v2 is a delivery adapter, not a re-plumbing."""

    # --- ML providers (§13) ---
    model_registry_path: str = "ml/registry"
    embedding_backend: str = "Facenet"  # DeepFace config string (§9: swappable by design)
    embedding_dimensions: int = 512

    # --- Observability (§21) ---
    log_level: str = "INFO"
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""
    metrics_enabled: bool = True

    # --- Rate limits (§18) ---
    rate_limit_otp_per_hour: int = 5
    rate_limit_swipes_per_minute: int = 60
    rate_limit_messages_per_minute: int = 30
    rate_limit_bids_per_minute: int = 20

    #: Minimum production secret length. A HS256 key shorter than its 256-bit output is the
    #: weak link in the whole §5 token scheme.
    MIN_PRODUCTION_SECRET_LENGTH: int = 32

    @model_validator(mode="after")
    def _reject_dev_secrets_in_production(self) -> Settings:
        if self.environment == "production":
            weak = (
                self.jwt_secret.startswith("dev-only")
                or "test" in self.jwt_secret.lower()
                or len(self.jwt_secret) < self.MIN_PRODUCTION_SECRET_LENGTH
            )
            if weak:
                raise ValueError(
                    "JWT_SECRET must be a real secret of at least "
                    f"{self.MIN_PRODUCTION_SECRET_LENGTH} characters in production"
                )
            if not self.mongodb_uri.startswith("mongodb+srv://"):
                raise ValueError(
                    "production requires a MongoDB Atlas connection string "
                    "(mongodb+srv://) — §9 duplicate detection depends on Atlas Vector Search"
                )
            if self.dev_auto_approve_verification:
                raise ValueError(
                    "DEV_AUTO_APPROVE_VERIFICATION cannot be enabled in production — it would "
                    "admit accounts with no verification at all, bypassing FR-1.6 entirely"
                )
        return self


class Thresholds(BaseSettings):
    """Product thresholds — every launch default flagged for post-launch refinement.

    §2 requires these be changeable without a redeploy, so :class:`ThresholdStore` persists
    overrides in MongoDB. The values here are the documented launch defaults; ``(DECIDED)``
    marks values the decision record fixed, as opposed to illustrative ones.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Admission & ratio (FR-2) ---
    h3_resolution: int = 6
    """FR-2.1 (DECIDED). Validated against real 30-day-active data at soft launch (§25 phase 2)."""

    ratio_upper_band: float = 1.05
    """FR-2.4 (DECIDED): freeze male admissions at active_men <= active_women * 1.05."""

    ratio_lower_band: float = 0.95
    """FR-2.4 (DECIDED): resume when women recover past * 0.95. The gap is the hysteresis."""

    admission_buffer: float = 0.93
    """FR-2.5 (DECIDED): admit men up to ~90-95% of active-women count."""

    queue_split_free: Ratio = 0.60
    queue_split_paid: Ratio = 0.25
    queue_split_auction: Ratio = 0.15
    """FR-2.7 (DECIDED): 60/25/15, all drawing from the same ratio ceiling."""

    active_window_days: int = 30
    """FR-2.3 (DECIDED): active = logged in within 30 days AND >=1 swipe in that window."""

    auction_window_start_hour: int = 19
    auction_window_end_hour: int = 20
    """FR-2.9: once daily, fixed window (DECIDED). Exact time is an OPEN item (README.md:361)."""

    paid_queue_price_paise: int = 49_900
    """FR-2.8 (DECIDED): fixed price, no surge. Exact figure is an OPEN item (README.md:361)."""

    auction_min_bid_paise: int = 10_000

    # --- Matching (FR-3, §12) ---
    daily_match_count: int = 15
    """FR-3.1 (DECIDED): 15 curated matches/day."""

    daily_match_count_basic_pro: int = 30
    daily_match_count_pro_plus: int = 40
    """FR-6.1 illustrative Pro tier allowances."""

    radius_min_km: int = 1
    radius_max_km: int = 100
    """FR-3.2 (DECIDED) slider bounds."""

    graduation_swipes: int = 20
    graduation_matches: int = 3
    """FR-3.4 (DECIDED): graduation at 20+ swipes AND 3+ matches."""

    exploration_rate_pre_graduation: Ratio = 0.40
    exploration_rate_post_graduation: Ratio = 0.15
    """FR-3.5 (DECIDED shape, illustrative %)."""

    confidence_mature_swipes: int = 200
    """N_mature in confidence(n) = min(1, log(1+n)/log(1+N_mature)) — §12, tunable."""

    candidate_pool_cap: int = 3_000
    """§19: pools capped before scoring keeps the nightly batch linear per user."""

    # --- §12 ranking weights. Structure is DECIDED; weights illustrative except visual. ---
    weight_cold_preference: float = 0.45
    weight_cold_demographic: float = 0.30
    weight_cold_prompt: float = 0.25

    weight_final_reciprocity: float = 0.35
    weight_final_collaborative: float = 0.25
    weight_final_preference: float = 0.20
    weight_final_engagement: float = 0.10
    weight_final_freshness: float = 0.05
    weight_final_visual: float = 0.05
    """FR-3.6 (DECIDED): visual-pattern weight is FIXED at 0.05. Do not tune."""

    visual_similarity_cap: float = 0.95
    """FR-3.6 (DECIDED): capped/discounted above 0.95 cosine (near-identical = suspicious)."""

    visual_similarity_neutral: float = 0.5
    """FR-3.6 (DECIDED): neutral 0.5 when like-history is too thin to infer a pattern."""

    freshness_halflife_days: float = 7.0

    # --- Identity (FR-1) ---
    duplicate_similarity_threshold: float = 0.90
    """FR-1.4 (DECIDED): >90% cosine -> human review. NEVER auto-ban."""

    photo_selfie_match_threshold: float = 0.65
    """FR-1.5: profile-photo-to-verification-selfie match floor."""

    bot_risk_auto_approve_below: float = 0.30
    bot_risk_auto_reject_above: float = 0.80
    """FR-1.6 (DECIDED): 3-band routing; the middle band is human review only."""

    # --- Anti-abuse (FR-5) ---
    dwell_threshold_ms: int = 10_000
    """FR-5.2 (DECIDED launch default): <10s dwell."""

    dwell_ratio: float = 0.70
    """FR-5.2 (DECIDED launch default): on >70% of right-swipes."""

    dwell_window_swipes: int = 100
    dwell_min_swipes_to_evaluate: int = 25
    """Rolling window; too few swipes cannot establish a pattern."""

    warnings_before_ban: int = 3
    """FR-5.3 (DECIDED): 3 warnings on SEPARATE occasions, then ban."""

    warning_separate_occasion_hours: int = 24
    """"Separate occasions" (FR-5.3) — two trips inside this window are one occasion."""

    # --- Chat & We-Met (FR-4) ---
    wemet_trigger_messages: int = 20
    wemet_trigger_messages_max: int = 30
    wemet_trigger_window_days: int = 3
    """FR-4.3 (DECIDED): 20-30 total messages within a 3-day window, no per-day minimum."""

    wemet_reask_days_min: int = 7
    wemet_reask_days_max: int = 14
    """FR-4.3 (DECIDED): re-fires every 1-2 weeks on "not yet met"."""

    # --- Retention (FR-7, §8, §18). All DECIDED, pending legal confirmation. ---
    grace_period_days: int = 30
    """§6: 30-day recoverable soft-delete, then hard delete."""

    message_retention_days_post_unmatch: int = 90
    """§8 (DECIDED); investigation holds pause this clock."""

    device_signal_retention_days: int = 90
    verification_capture_retention_days: int = 30
    payment_record_retention_years: int = 7
    """§18 (DECIDED): payment records survive the deletion cascade per financial regulation."""

    # --- Monetization (FR-6) ---
    pro_basic_price_paise: int = 79_900
    pro_plus_price_paise: int = 149_900
    """FR-6.1: exact pricing is an OPEN item (README.md:361)."""

    gst_rate: float = 0.18
    """FR-6.5: place-of-supply split into CGST/SGST or IGST at invoice time."""

    @model_validator(mode="after")
    def _validate_invariants(self) -> Thresholds:
        # FR-2.4: the hysteresis band must actually be a band, or the state machine flaps.
        if self.ratio_lower_band >= self.ratio_upper_band:
            raise ValueError(
                "ratio_lower_band must be strictly below ratio_upper_band — a zero-width "
                "band is not hysteresis and will flap (FR-2.4)"
            )
        # FR-2.7: the three tiers partition one ceiling; they must sum to exactly 1.
        split_total = self.queue_split_free + self.queue_split_paid + self.queue_split_auction
        if abs(split_total - 1.0) > 1e-9:
            raise ValueError(f"queue splits must sum to 1.0, got {split_total} (FR-2.7)")
        # §12: final_score weights must sum to 1 or scores stop being comparable across users.
        final_total = (
            self.weight_final_reciprocity
            + self.weight_final_collaborative
            + self.weight_final_preference
            + self.weight_final_engagement
            + self.weight_final_freshness
            + self.weight_final_visual
        )
        if abs(final_total - 1.0) > 1e-9:
            raise ValueError(f"final_score weights must sum to 1.0, got {final_total} (§12)")
        cold_total = (
            self.weight_cold_preference
            + self.weight_cold_demographic
            + self.weight_cold_prompt
        )
        if abs(cold_total - 1.0) > 1e-9:
            raise ValueError(f"cold_start_score weights must sum to 1.0, got {cold_total} (§12)")
        # FR-3.6: the visual weight is DECIDED-fixed. Guard it against well-meaning tuning.
        if abs(self.weight_final_visual - 0.05) > 1e-9:
            raise ValueError(
                "weight_final_visual is fixed at 0.05 by decision record (FR-3.6) — not tunable"
            )
        # FR-1.6: the bands must leave a human-review middle, not meet or cross.
        if self.bot_risk_auto_approve_below >= self.bot_risk_auto_reject_above:
            raise ValueError(
                "bot-risk bands must leave a human-review middle band (FR-1.6)"
            )
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-lifetime infrastructure settings."""
    return Settings()


@functools.lru_cache(maxsize=1)
def get_default_thresholds() -> Thresholds:
    """Launch-default thresholds as seeded from the environment.

    This is the *baseline*. Runtime code should read through
    :class:`sincere.shared.threshold_store.ThresholdStore` instead, which layers
    admin-applied overrides on top of these defaults.
    """
    return Thresholds()
