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
    # Recycle worker processes periodically so a wedged/leaky child can't sit
    # dead forever silently swallowing the queue.
    worker_max_tasks_per_child=500,
    timezone="UTC",
    enable_utc=True,
    imports=("tradingagents.worker.jobs", "tradingagents.worker.queue_tasks"),
    beat_schedule={
        # `expires` is what prevents a backlog: these periodic tasks are pure
        # "do the current work now" pollers — a stale copy is worthless because
        # the next tick redoes it. If no worker consumes one within a few ticks
        # it expires and is discarded on receipt instead of piling up in Redis
        # and forcing a recovering worker to grind through thousands of them.
        "dispatch-queued-analysis-runs": {
            "task": "tradingagents.worker.queue_tasks.dispatch_queued_runs_task",
            "schedule": settings.dispatch_interval_seconds,
            "options": {"expires": max(settings.dispatch_interval_seconds * 5, 10)},
        },
        "sweep-stale-analysis-runs": {
            "task": "tradingagents.worker.queue_tasks.sweep_stale_runs_task",
            "schedule": max(settings.worker_stale_after_seconds // 3, 10),
            "options": {"expires": max(settings.worker_stale_after_seconds // 3, 10)},
        },
    },
)
