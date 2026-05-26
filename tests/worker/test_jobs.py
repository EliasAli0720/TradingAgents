import json
from datetime import date

from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.serialization import extract_reports, json_safe_state
from tradingagents.worker.jobs import execute_analysis_run


def _repo():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    return session, AnalysisRunRepository(session)


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
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts):
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": ticker},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    assert repo.get_run(run.run_id).status == "succeeded"
    assert repo.get_result(run.run_id).decision == "Hold"


def test_execute_analysis_run_failure_writes_error():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts):
        raise RuntimeError("provider failed")

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert saved.error == "provider failed"
