from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from tradingagents.api.db import SessionLocal
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.analysis import run_tradingagents_analysis
from tradingagents.worker.celery_app import celery_app


AnalysisExecutor = Callable[[str, date, str, list[str]], dict[str, Any]]


def execute_analysis_run(
    repo: AnalysisRunRepository,
    run_id: str,
    executor: AnalysisExecutor = run_tradingagents_analysis,
) -> None:
    run = repo.get_run(run_id)
    if run is None or run.status != "queued":
        return

    try:
        repo.mark_running(run_id)
        repo.session.commit()
        output = executor(run.ticker, run.trade_date, run.asset_type, run.analysts)
        repo.store_success(
            run_id=run_id,
            decision=output["decision"],
            reports=output["reports"],
            final_state=output["final_state"],
        )
        repo.session.commit()
    except Exception as exc:
        repo.session.rollback()
        repo.store_failure(run_id, str(exc))
        repo.session.commit()


@celery_app.task(name="tradingagents.worker.jobs.run_analysis_task")
def run_analysis_task(run_id: str) -> None:
    with SessionLocal() as session:
        repo = AnalysisRunRepository(session)
        execute_analysis_run(repo, run_id)
