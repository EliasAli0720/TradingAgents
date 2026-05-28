from __future__ import annotations

from tradingagents.api.config import get_api_settings
from tradingagents.api.db import SessionLocal
from tradingagents.worker.celery_app import celery_app
from tradingagents.worker.dispatcher import DispatchConfig, dispatch_once
from tradingagents.worker.jobs import run_analysis_task
from tradingagents.worker.sweeper import sweep_once


def _enqueue_analysis_task(run_id: str) -> str | None:
    result = run_analysis_task.apply_async(args=(run_id,))
    return result.id


@celery_app.task(name="tradingagents.worker.queue_tasks.dispatch_queued_runs_task")
def dispatch_queued_runs_task() -> int:
    settings = get_api_settings()
    with SessionLocal() as session:
        return dispatch_once(
            session,
            _enqueue_analysis_task,
            DispatchConfig(
                system_running=settings.max_running_system,
                user_running=settings.max_running_per_user,
                lease_seconds=settings.run_lease_seconds,
            ),
        )


@celery_app.task(name="tradingagents.worker.queue_tasks.sweep_stale_runs_task")
def sweep_stale_runs_task() -> int:
    settings = get_api_settings()
    with SessionLocal() as session:
        repaired = sweep_once(
            session,
            stale_after_seconds=settings.worker_stale_after_seconds,
        )
        session.commit()
        return repaired
