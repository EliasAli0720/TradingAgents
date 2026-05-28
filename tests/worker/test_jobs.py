import json
import subprocess
import sys
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.crypto import encrypt_secret
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.repositories import utcnow
from tradingagents.api.serialization import extract_reports, json_safe_state
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.worker.analysis import run_tradingagents_analysis
from tradingagents.worker.celery_app import celery_app
from tradingagents.worker.jobs import execute_analysis_run


FERNET_KEY = "dBBj0g2y16HOVnBCwG9r20eyHmxtPXgvBXVHfJfRB4U="


def _repo():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisRunRepository(session)


def _dispatch_run(repo: AnalysisRunRepository, run_id: str) -> None:
    repo.claim_next_queued_for_dispatch(
        user_id=repo.require_run(run_id).user_id,
        lease_expires_at=utcnow() + timedelta(seconds=600),
    )


LLM_CONFIG = {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "backend_url": None,
}


def test_extract_reports_keeps_expected_report_keys():
    state = {
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_plan": "plan",
        "trader_investment_plan": "trade",
        "final_trade_decision": "Rating: Hold",
    }
    reports = extract_reports(state)
    assert reports == state


def test_json_safe_state_drops_messages_and_stringifies_unknown_objects():
    class Unknown:
        def __str__(self):
            return "unknown-object"

    state = {"messages": [object()], "ticker": "NVDA", "value": Unknown()}
    safe = json_safe_state(state)
    assert "messages" not in safe
    assert safe["ticker"] == "NVDA"
    assert safe["value"] == "unknown-object"


def test_json_safe_state_returns_strict_json_for_nested_values():
    class Unknown:
        def __str__(self):
            return "nested-object"

    state = {
        "messages": [object()],
        "metadata": {
            "published_on": date(2026, 1, 15),
            "scores": (1.0, float("nan"), float("inf"), float("-inf")),
            "custom": Unknown(),
        },
    }

    safe = json_safe_state(state)

    json.dumps(safe, allow_nan=False)
    assert safe["metadata"]["published_on"] == "2026-01-15"
    assert safe["metadata"]["scores"] == [1.0, "nan", "inf", "-inf"]
    assert safe["metadata"]["custom"] == "nested-object"


def test_execute_analysis_run_success_writes_result():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA", date(2026, 1, 15), "stock", ["market"], llm_config=LLM_CONFIG
    )
    _dispatch_run(repo, run.run_id)
    session.commit()
    calls = []

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
        calls.append((ticker, trade_date, asset_type, analysts, llm_config))
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": ticker},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    assert repo.get_run(run.run_id).status == "succeeded"
    assert repo.get_result(run.run_id).decision == "Hold"
    assert calls == [("NVDA", date(2026, 1, 15), "stock", ["market"], LLM_CONFIG)]
    assert [event.event_type for event in repo.list_events(run.run_id)] == [
        "run_queued",
        "run_dispatching",
        "run_started",
        "run_progress",
        "run_progress",
        "run_progress",
        "run_succeeded",
    ]


def test_successful_worker_persists_report_artifact_metadata():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config=LLM_CONFIG,
    )
    _dispatch_run(repo, run.run_id)
    session.commit()

    def fake_executor(*args, **kwargs):
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {
                "company_of_interest": "NVDA",
                "final_trade_decision": "Rating: Hold",
            },
            "artifacts": [
                {
                    "kind": "report_md",
                    "storage_key": f"{run.run_id}/reports/complete_report.md",
                }
            ],
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    artifacts = repo.list_artifacts(run.run_id)
    assert [artifact.kind for artifact in artifacts] == ["report_md"]
    assert artifacts[0].storage_key == f"{run.run_id}/reports/complete_report.md"


def test_execute_analysis_run_requires_dispatched_run():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA", date(2026, 1, 15), "stock", ["market"], llm_config=LLM_CONFIG
    )
    session.commit()

    execute_analysis_run(
        repo,
        run.run_id,
        lambda *args: {"decision": "Hold", "reports": {}, "final_state": {}},
    )
    session.commit()

    assert repo.get_run(run.run_id).status == "queued"
    assert repo.get_result(run.run_id) is None


def test_execute_analysis_run_emits_user_friendly_progress_events():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA", date(2026, 1, 15), "stock", ["market"], llm_config=LLM_CONFIG
    )
    _dispatch_run(repo, run.run_id)
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": ticker},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    events = repo.list_events(run.run_id)
    progress_events = [event for event in events if event.event_type == "run_progress"]
    assert [event.payload["phase"] for event in progress_events] == [
        "preparing",
        "analyzing",
        "saving",
    ]
    assert [event.payload["percent"] for event in progress_events] == [15, 35, 85]
    assert all(event.payload["message"] for event in progress_events)
    assert [event.event_type for event in events] == [
        "run_queued",
        "run_dispatching",
        "run_started",
        "run_progress",
        "run_progress",
        "run_progress",
        "run_succeeded",
    ]
    assert repo.get_run(run.run_id).current_step == "Completed"


def test_execute_analysis_run_failure_writes_error():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA", date(2026, 1, 15), "stock", ["market"], llm_config=LLM_CONFIG
    )
    _dispatch_run(repo, run.run_id)
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert saved.error == "provider failed"
    assert repo.list_events(run.run_id)[-1].event_type == "run_failed"


def test_execute_analysis_run_claims_queued_run_once():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA", date(2026, 1, 15), "stock", ["market"], llm_config=LLM_CONFIG
    )
    session.commit()

    claimed = repo.claim_queued_run(run.run_id)
    session.commit()

    assert claimed is not None
    assert repo.claim_queued_run(run.run_id) is None


def test_execute_analysis_run_without_model_config_marks_failed():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    _dispatch_run(repo, run.run_id)
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
        raise AssertionError("executor should not run")

    with pytest.raises(RuntimeError, match="model settings snapshot missing"):
        execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert saved.error == "model settings snapshot missing"


def test_execute_analysis_run_does_not_overwrite_cancelled_run_after_executor_returns():
    session, repo = _repo()
    run = repo.create_run(
        "NVDA", date(2026, 1, 15), "stock", ["market"], llm_config=LLM_CONFIG
    )
    _dispatch_run(repo, run.run_id)
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
        repo.cancel_run(run.run_id, "user requested cancellation")
        session.commit()
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": ticker},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "cancelled"
    assert repo.get_result(run.run_id) is None
    assert [event.event_type for event in repo.list_events(run.run_id)] == [
        "run_queued",
        "run_dispatching",
        "run_started",
        "run_progress",
        "run_progress",
        "run_cancelling",
        "run_cancelled",
    ]


def test_celery_app_registers_analysis_task():
    script = (
        "from tradingagents.worker.celery_app import celery_app;"
        "celery_app.loader.import_default_modules();"
        "expected = {"
        "'tradingagents.worker.jobs.run_analysis_task',"
        "'tradingagents.worker.queue_tasks.dispatch_queued_runs_task',"
        "'tradingagents.worker.queue_tasks.sweep_stale_runs_task',"
        "};"
        "assert expected.issubset(celery_app.tasks)"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_celery_app_uses_queue_safe_worker_defaults():
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.broker_connection_retry_on_startup is True
    assert "dispatch-queued-analysis-runs" in celery_app.conf.beat_schedule
    assert "sweep-stale-analysis-runs" in celery_app.conf.beat_schedule


def test_run_tradingagents_analysis_decrypts_user_api_key_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setitem(
        sys.modules["tradingagents.worker.analysis"].DEFAULT_CONFIG,
        "reports_dir",
        str(tmp_path / "reports"),
    )
    captured_configs = []

    class FakeGraph:
        def __init__(self, selected_analysts, config):
            captured_configs.append((selected_analysts, config))

        def propagate(self, ticker, trade_date, asset_type):
            return ({"final_trade_decision": "Hold"}, "Hold")

    monkeypatch.setattr("tradingagents.worker.analysis.TradingAgentsGraph", FakeGraph)
    llm_config = {
        **LLM_CONFIG,
        "api_key_encrypted": encrypt_secret("sk-user-abcdef123456"),
    }

    output = run_tradingagents_analysis(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        llm_config,
    )

    assert output["decision"] == "Hold"
    assert captured_configs[0][0] == ["market"]
    assert captured_configs[0][1]["api_key"] == "sk-user-abcdef123456"


def test_run_tradingagents_analysis_writes_markdown_report(monkeypatch, tmp_path):
    reports_dir = tmp_path / "reports"
    monkeypatch.setitem(
        sys.modules["tradingagents.worker.analysis"].DEFAULT_CONFIG,
        "reports_dir",
        str(reports_dir),
    )

    class FakeGraph:
        def __init__(self, selected_analysts, config):
            pass

        def propagate(self, ticker, trade_date, asset_type):
            return (
                {
                    "market_report": "market body",
                    "sentiment_report": "sentiment body",
                    "news_report": "news body",
                    "fundamentals_report": "fundamentals body",
                    "investment_plan": "investment plan body",
                    "investment_debate_state": {
                        "bull_history": "bull body",
                        "bear_history": "bear body",
                        "judge_decision": "research manager body",
                    },
                    "trader_investment_plan": "trader body",
                    "risk_debate_state": {
                        "aggressive_history": "aggressive body",
                        "conservative_history": "conservative body",
                        "neutral_history": "neutral body",
                        "judge_decision": "portfolio body",
                    },
                    "final_trade_decision": "portfolio body",
                },
                "Hold",
            )

    monkeypatch.setattr("tradingagents.worker.analysis.TradingAgentsGraph", FakeGraph)

    output = run_tradingagents_analysis(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        LLM_CONFIG,
    )

    run_dirs = list(reports_dir.glob("NVDA_*"))
    assert output["decision"] == "Hold"
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "complete_report.md").read_text(encoding="utf-8").startswith(
        "# Trading Analysis Report: NVDA"
    )
    assert (run_dirs[0] / "1_analysts" / "market.md").read_text(encoding="utf-8") == "market body"
    assert (run_dirs[0] / "2_research" / "manager.md").read_text(encoding="utf-8") == "research manager body"
    assert (run_dirs[0] / "3_trading" / "trader.md").read_text(encoding="utf-8") == "trader body"
    assert (run_dirs[0] / "5_portfolio" / "decision.md").read_text(encoding="utf-8") == "portfolio body"


def test_run_tradingagents_analysis_with_run_id_writes_isolated_artifacts(
    monkeypatch,
    tmp_path,
):
    reports_dir = tmp_path / "reports"
    monkeypatch.setitem(
        sys.modules["tradingagents.worker.analysis"].DEFAULT_CONFIG,
        "reports_dir",
        str(reports_dir),
    )

    class FakeGraph:
        def __init__(self, selected_analysts, config):
            pass

        def propagate(self, ticker, trade_date, asset_type):
            return ({"final_trade_decision": "Rating: Hold"}, "Hold")

    monkeypatch.setattr("tradingagents.worker.analysis.TradingAgentsGraph", FakeGraph)

    output = run_tradingagents_analysis(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        LLM_CONFIG,
        run_id="run_artifacts",
    )

    storage_keys = [artifact.storage_key for artifact in output["artifacts"]]
    assert "run_artifacts/reports/complete_report.md" in storage_keys
    assert (
        reports_dir / "run_artifacts" / "reports" / "complete_report.md"
    ).read_text(encoding="utf-8").startswith("# Trading Analysis Report: NVDA")


def test_trading_graph_provider_kwargs_include_snapshot_api_key():
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "llm_provider": "openai",
        "api_key": "sk-user-abcdef123456",
        "openai_reasoning_effort": "low",
    }

    assert graph._get_provider_kwargs()["api_key"] == "sk-user-abcdef123456"
    assert graph._get_provider_kwargs()["reasoning_effort"] == "low"


def _seed_succeeded_run(repo, *, user_language="zh"):
    """Create a user, a run owned by them, and store an English result."""
    from tradingagents.api.models import User
    from tradingagents.api.repositories import utcnow as _utcnow

    repo.session.add(
        User(
            user_id="usr_1",
            username="u1",
            password_hash="h",
            role="operator",
            is_active=True,
            language=user_language,
            created_at=_utcnow(),
        )
    )
    run = repo.create_run(
        "NVDA", date(2026, 1, 15), "stock", ["market"],
        user_id="usr_1", llm_config=LLM_CONFIG,
    )
    _dispatch_run(repo, run.run_id)
    repo.session.commit()

    def fake_executor(*args, **kwargs):
        return {
            "decision": "Hold",
            "reports": {
                "market_report": "## Market\nEnglish body",
                "final_trade_decision": "**Rating**: HOLD",
            },
            "final_state": {"company_of_interest": "NVDA"},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    repo.session.commit()
    return run


class _FakeTranslator:
    def translate(self, markdown, *, target_lang):
        return f"[{target_lang}] {markdown}"


def test_translate_section_stores_translation_and_keeps_english():
    from tradingagents.worker.jobs import translate_section

    session, repo = _repo()
    run = _seed_succeeded_run(repo, user_language="zh")

    translate_section(
        repo, run.run_id, "zh", "market_report", "## Market\nEnglish body",
        translator_factory=lambda repo, run: _FakeTranslator(),
    )
    session.commit()

    # English untouched
    assert repo.get_result(run.run_id).reports["market_report"] == "## Market\nEnglish body"
    # Chinese translation lands in the staging table, assembled by get_translations
    translations = repo.get_translations(run.run_id)
    assert translations["zh"]["market_report"].startswith("[zh] ## Market")
    assert "section_translated" in [e.event_type for e in repo.list_events(run.run_id)]


def test_translate_section_is_idempotent():
    from tradingagents.worker.jobs import translate_section

    session, repo = _repo()
    run = _seed_succeeded_run(repo, user_language="zh")

    calls = []

    def factory(repo, run):
        calls.append(run.run_id)
        return _FakeTranslator()

    translate_section(repo, run.run_id, "zh", "market_report", "body", translator_factory=factory)
    session.commit()
    # Second call for the same section must skip (already translated).
    translate_section(repo, run.run_id, "zh", "market_report", "body", translator_factory=factory)
    session.commit()

    assert len(calls) == 1


def test_run_target_language_skips_english_owner():
    from tradingagents.worker.jobs import _run_target_language

    session, repo = _repo()
    run = _seed_succeeded_run(repo, user_language="en")

    assert _run_target_language(repo, repo.require_run(run.run_id)) is None
