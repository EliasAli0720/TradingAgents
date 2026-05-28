from __future__ import annotations

from celery import Celery

from tradingagents.api.config import get_api_settings


settings = get_api_settings()

celery_app = Celery(
    "tradingagents",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=settings.task_time_limit_seconds,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    timezone="UTC",
    enable_utc=True,
    imports=("tradingagents.worker.jobs", "tradingagents.worker.queue_tasks"),
    beat_schedule={
        "dispatch-queued-analysis-runs": {
            "task": "tradingagents.worker.queue_tasks.dispatch_queued_runs_task",
            "schedule": settings.dispatch_interval_seconds,
        },
        "sweep-stale-analysis-runs": {
            "task": "tradingagents.worker.queue_tasks.sweep_stale_runs_task",
            "schedule": max(settings.worker_stale_after_seconds // 3, 10),
        },
    },
)
