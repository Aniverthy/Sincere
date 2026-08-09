"""Celery application — the job runtime for TECHNICAL_IMPLEMENTATION_PLAN.md §15b.

Same codebase as the API, separate entrypoint (§3 diagram). Seven scheduled jobs, each owned
by the module whose domain it belongs to; this file only declares the schedule and the
reliability policy.

§15:660 sets the bar those jobs must clear: "idempotent (safe re-run), per-region parallelizable
(match batch), dead-letter + alerting on repeated failure (a silently skipped auction close or
retention purge is a business/legal incident, not just a bug)."

Run:  celery -A sincere.jobs.celery_app worker --loglevel=info
      celery -A sincere.jobs.celery_app beat  --loglevel=info
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging, task_failure

from sincere.shared.config import get_default_thresholds, get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
thresholds = get_default_thresholds()

celery_app = Celery(
    "sincere",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "sincere.identity.jobs",
        "sincere.admission.jobs",
        "sincere.matching.jobs",
        "sincere.chat.jobs",
        "sincere.antiabuse.jobs",
        "sincere.monetization.jobs",
        "sincere.feedback_ml.jobs",
        "sincere.admin.jobs",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",  # single-city India launch (§25 phase 2)
    enable_utc=True,
    # §15:660 — every job must be safe to re-run, so late acknowledgement plus redelivery
    # on worker loss is the correct trade: a duplicate run is harmless, a skipped run is not.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=60,
    task_max_retries=5,
    result_expires=60 * 60 * 24,
    # Dead-letter routing: repeated failures land here and §21 alerts on depth.
    task_routes={
        "sincere.admission.jobs.close_auction": {"queue": "critical"},
        "sincere.admin.jobs.retention_cleanup": {"queue": "critical"},
        "sincere.matching.jobs.*": {"queue": "batch"},
        "sincere.feedback_ml.jobs.retrain_models": {"queue": "ml"},
    },
)


# ---------------------------------------------------------------------------
# The seven scheduled jobs of §15b
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # 1. Daily 15 match-generation batch — nightly per region, before delivery time.
    "daily-match-batch": {
        "task": "sincere.matching.jobs.generate_daily_batches",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "batch"},
    },
    # 2. Daily auction close — at the fixed window end (FR-2.9).
    #    §21 pages immediately on failure or latency here.
    "auction-close": {
        "task": "sincere.admission.jobs.close_auction",
        "schedule": crontab(hour=thresholds.auction_window_end_hour, minute=0),
        "options": {"queue": "critical"},
    },
    # 3. Ratio/hysteresis recompute — event-triggered in-band; this hourly sweep is the
    #    §19 drift-correction backstop against counter drift.
    "ratio-recompute": {
        "task": "sincere.admission.jobs.recompute_all_ratios",
        "schedule": crontab(minute=15),
    },
    # 4. Churn-risk flagging — daily scan (§13: heuristic at launch, women prioritized).
    "churn-risk-scan": {
        "task": "sincere.admission.jobs.flag_churn_risk",
        "schedule": crontab(hour=6, minute=30),
    },
    # 5. Batch model retraining — weekly; cadence TBD by volume (FR-4.4).
    "model-retrain": {
        "task": "sincere.feedback_ml.jobs.retrain_models",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),
        "options": {"queue": "ml"},
    },
    # 6. We-Met prompt scheduler — continuous trigger checks + re-ask timers (FR-4.3).
    "wemet-scheduler": {
        "task": "sincere.feedback_ml.jobs.schedule_wemet_prompts",
        "schedule": crontab(minute="*/30"),
    },
    # 7. Retention cleanup — 30-day grace hard-deletes, 90-day post-unmatch message purge
    #    honoring investigation holds, 90-day device-signal purge. ANY failure alerts (§21).
    "retention-cleanup": {
        "task": "sincere.admin.jobs.retention_cleanup",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "critical"},
    },
    # Infrastructure backstop, not one of the seven: re-dispatch outbox events whose
    # in-process handlers failed, preserving the §14 at-least-once guarantee.
    "outbox-sweeper": {
        "task": "sincere.admin.jobs.sweep_outbox",
        "schedule": crontab(minute="*/5"),
    },
    # Also not one of the seven, but required by FR-6.1: a subscription past its renewal date
    # must stop granting entitlement. FR-6.4 keeps the free 15/day regardless.
    "subscription-expiry": {
        "task": "sincere.monetization.jobs.expire_subscriptions",
        "schedule": crontab(hour=5, minute=0),
    },
}


@setup_logging.connect
def _configure_worker_logging(**_: object) -> None:
    """Use the §22 structured JSON logger in workers too, not Celery's default format."""
    from sincere.shared.logging import configure_logging

    configure_logging()


@task_failure.connect
def _alert_on_failure(sender=None, task_id=None, exception=None, **_: object) -> None:
    """§15:660 — repeated failure of a critical job is a business/legal incident.

    Logged at ERROR with the task name so §21's alerting can route on it. The critical-queue
    tasks (auction close, retention cleanup) are the ones that page.
    """
    name = getattr(sender, "name", "unknown")
    critical = name in {
        "sincere.admission.jobs.close_auction",
        "sincere.admin.jobs.retention_cleanup",
    }
    logger.error(
        "job.failed",
        extra={
            "task": name,
            "task_id": task_id,
            "error": str(exception),
            "critical": critical,
            "alert": "page" if critical else "ticket",
        },
    )
