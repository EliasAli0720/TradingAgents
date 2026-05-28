from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from tradingagents.api.db import SessionLocal
from tradingagents.api.config import get_api_settings
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.analysis import run_tradingagents_analysis
from tradingagents.worker.celery_app import celery_app
from tradingagents.worker.heartbeat import heartbeat


AnalysisExecutor = Callable[[str, date, str, list[str], dict[str, Any]], dict[str, Any]]


def execute_analysis_run(
    repo: AnalysisRunRepository,
    run_id: str,
    executor: AnalysisExecutor = run_tradingagents_analysis,
    heartbeat_interval_seconds: int | None = None,
) -> None:
    run = repo.start_dispatched_run(run_id)
    if run is None:
        return

    try:
        repo.session.commit()
        if run.llm_config is None:
            raise RuntimeError("model settings snapshot missing")
        repo.record_progress(
            run_id,
            phase="preparing",
            step="Preparing analysis",
            percent=15,
            message="正在准备模型、数据源和智能体配置。",
        )
        repo.session.commit()
        repo.record_progress(
            run_id,
            phase="analyzing",
            step="Running agent analysis",
            percent=35,
            message="智能体正在分析行情、新闻、情绪和基本面。",
        )
        repo.session.commit()
        if heartbeat_interval_seconds is None:
            output = executor(
                run.ticker,
                run.trade_date,
                run.asset_type,
                run.analysts,
                run.llm_config,
            )
        else:
            with heartbeat(run_id, heartbeat_interval_seconds):
                output = executor(
                    run.ticker,
                    run.trade_date,
                    run.asset_type,
                    run.analysts,
                    run.llm_config,
                )
        repo.session.refresh(run)
        if run.status == "cancelled":
            repo.session.commit()
            return
        repo.record_progress(
            run_id,
            phase="saving",
            step="Saving analysis reports",
            percent=85,
            message="正在整理最终结论并保存 Markdown 报告。",
        )
        repo.session.commit()
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
        raise


@celery_app.task(name="tradingagents.worker.jobs.run_analysis_task")
def run_analysis_task(run_id: str) -> None:
    with SessionLocal() as session:
        repo = AnalysisRunRepository(session)
        settings = get_api_settings()
        execute_analysis_run(
            repo,
            run_id,
            heartbeat_interval_seconds=settings.worker_heartbeat_seconds,
        )
