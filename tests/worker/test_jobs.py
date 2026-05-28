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
        "run_cancelled",
    ]


def test_celery_app_registers_analysis_task():
    script = (
        "from tradingagents.worker.celery_app import celery_app;"
        "celery_app.loader.import_default_modules();"
        "assert 'tradingagents.worker.jobs.run_analysis_task' in celery_app.tasks"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


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
