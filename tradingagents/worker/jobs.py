from __future__ import annotations

from collections.abc import Callable
from datetime import date
from inspect import Parameter, signature
from typing import Any

from tradingagents.api.db import SessionLocal
from tradingagents.api.config import get_api_settings
from tradingagents.api.models import AnalysisRun, AnalysisRunResult, User
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.translation_settings_repository import (
    UserTranslationSettingsRepository,
)
from tradingagents.translation import build_llm_translator, build_translation_translator
from tradingagents.worker.analysis import run_tradingagents_analysis
from tradingagents.worker.celery_app import celery_app
from tradingagents.worker.cancellation import AnalysisCancelled
from tradingagents.worker.context import RunContext
from tradingagents.worker.heartbeat import heartbeat


AnalysisExecutor = Callable[..., dict[str, Any]]


def _execute_with_optional_run_id(
    executor: AnalysisExecutor,
    *,
    run_id: str,
    ticker: str,
    trade_date: date,
    asset_type: str,
    analysts: list[str],
    llm_config: dict[str, Any],
    on_section=None,
    context: RunContext | None = None,
) -> dict[str, Any]:
    try:
        parameters = list(signature(executor).parameters.values())
    except (TypeError, ValueError):
        parameters = []
    has_var_kw = any(p.kind == Parameter.VAR_KEYWORD for p in parameters)
    names = {p.name for p in parameters}
    kwargs: dict[str, Any] = {}
    if has_var_kw or "run_id" in names:
        kwargs["run_id"] = run_id
    if on_section is not None and (has_var_kw or "on_section" in names):
        kwargs["on_section"] = on_section
    if context is not None and (has_var_kw or "context" in names):
        kwargs["context"] = context
    return executor(ticker, trade_date, asset_type, analysts, llm_config, **kwargs)


def execute_analysis_run(
    repo: AnalysisRunRepository,
    run_id: str,
    executor: AnalysisExecutor = run_tradingagents_analysis,
    heartbeat_interval_seconds: int | None = None,
    on_section=None,
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
                on_section=on_section,
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
                    on_section=on_section,
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


def _run_target_language(repo: AnalysisRunRepository, run: AnalysisRun) -> str | None:
    """Owner's language, or None when translation should be skipped."""
    if run.llm_config is None:
        return None
    owner = repo.session.get(User, run.user_id)
    lang = owner.language if owner is not None else "zh"
    return None if lang == "en" else lang


def _default_translator_factory(repo: AnalysisRunRepository, run: AnalysisRun):
    """Prefer the user's dedicated translation model; fall back to the
    analysis model only when no translation model is configured."""
    tcfg = UserTranslationSettingsRepository(repo.session).snapshot(run.user_id)
    if tcfg is not None:
        return build_translation_translator(tcfg)
    return build_llm_translator(run.llm_config)


def translate_section(
    repo: AnalysisRunRepository,
    run_id: str,
    lang: str,
    section: str,
    text: str,
    translator_factory: Callable[[AnalysisRunRepository, AnalysisRun], Any] = _default_translator_factory,
) -> None:
    """Translate one report section and upsert it. Idempotent + best-effort.

    English originals are never touched. Already-translated sections are
    skipped so the mid-run callback and the post-success backfill don't
    double-translate.
    """
    if not text or not text.strip():
        return
    if repo.has_translation(run_id, lang, section):
        return
    run = repo.session.get(AnalysisRun, run_id)
    if run is None or run.llm_config is None:
        return
    translator = translator_factory(repo, run)
    try:
        translated = translator.translate(text, target_lang=lang)
    except Exception:  # noqa: BLE001 - one section failing must not abort others
        return
    repo.upsert_translation(run_id, lang, section, translated)
    repo.session.commit()


@celery_app.task(name="tradingagents.worker.jobs.translate_section_task")
def translate_section_task(run_id: str, lang: str, section: str, text: str) -> None:
    with SessionLocal() as session:
        repo = AnalysisRunRepository(session)
        translate_section(repo, run_id, lang, section, text)


@celery_app.task(name="tradingagents.worker.jobs.run_analysis_task")
def run_analysis_task(run_id: str) -> None:
    with SessionLocal() as session:
        repo = AnalysisRunRepository(session)
        settings = get_api_settings()

        run = repo.session.get(AnalysisRun, run_id)
        target_lang = _run_target_language(repo, run) if run is not None else None

        on_section = None
        if target_lang is not None:
            def on_section(section: str, text: str, _lang=target_lang) -> None:
                # Translate analyst reports the moment they appear, while the
                # rest of the pipeline is still running.
                translate_section_task.apply_async(args=(run_id, _lang, section, text))

        execute_analysis_run(
            repo,
            run_id,
            heartbeat_interval_seconds=settings.worker_heartbeat_seconds,
            on_section=on_section,
        )

        # Backfill: cover the final-wave sections (and any the mid-run callback
        # missed) once the English result is stored.
        run = repo.session.get(AnalysisRun, run_id)
        if target_lang is not None and run is not None and run.status == "succeeded":
            result = repo.session.get(AnalysisRunResult, run_id)
            if result is not None and result.reports:
                for section, text in result.reports.items():
                    if not isinstance(text, str) or not text.strip():
                        continue
                    if repo.has_translation(run_id, target_lang, section):
                        continue
                    translate_section_task.apply_async(
                        args=(run_id, target_lang, section, text)
                    )
