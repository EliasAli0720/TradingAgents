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
    imports=("tradingagents.worker.jobs",),
)
