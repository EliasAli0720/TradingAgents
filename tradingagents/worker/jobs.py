from __future__ import annotations

from collections.abc import Callable
from datetime import date
from inspect import Parameter, signature
from typing import Any

from tradingagents.api.db import SessionLocal
from tradingagents.api.config import get_api_settings
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.analysis import run_tradingagents_analysis
from tradingagents.worker.celery_app import celery_app
from tradingagents.worker.cancellation import AnalysisCancelled
from tradingagents.worker.heartbeat import heartbeat


AnalysisExecutor = Callable[[str, date, str, list[str], dict[str, Any]], dict[str, Any]]


def _execute_with_optional_run_id(
    executor: AnalysisExecutor,
    *,
    run_id: str,
    ticker: str,
    trade_date: date,
    asset_type: str,
    analysts: list[str],
    llm_config: dict[str, Any],
) -> dict[str, Any]:
    try:
        parameters = signature(executor).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    accepts_run_id = any(
        parameter.kind == Parameter.VAR_KEYWORD or parameter.name == "run_id"
        for parameter in parameters
    )
    if accepts_run_id:
        return executor(
            ticker,
            trade_date,
            asset_type,
            analysts,
            llm_config,
            run_id=run_id,
        )
    return executor(ticker, trade_date, asset_type, analysts, llm_config)


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
            output = _execute_with_optional_run_id(
                executor,
                run_id=run_id,
                ticker=run.ticker,
                trade_date=run.trade_date,
                asset_type=run.asset_type,
                analysts=run.analysts,
                llm_config=run.llm_config,
            )
        else:
            with heartbeat(run_id, heartbeat_interval_seconds):
                output = _execute_with_optional_run_id(
                    executor,
                    run_id=run_id,
                    ticker=run.ticker,
                    trade_date=run.trade_date,
                    asset_type=run.asset_type,
                    analysts=run.analysts,
                    llm_config=run.llm_config,
                )
        repo.session.refresh(run)
        if run.status in {"cancelled", "cancelling"}:
            if run.status == "cancelling":
                repo.mark_cancelled(run_id, "analysis cancelled")
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
        for artifact in output.get("artifacts") or []:
            repo.add_artifact(run_id, artifact)
        repo.session.commit()
    except AnalysisCancelled:
        repo.session.rollback()
        repo.mark_cancelled(run_id, "analysis cancelled")
        repo.session.commit()
        raise
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
