from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import RunEventRepository, RunRepository
from tradingagents.worker.jobs import run_fake_analysis


def test_fake_analysis_job_completes_run(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.create_run("SPY", "2026-05-19", "stock", {"ticker": "SPY"})

    run_fake_analysis(run["id"], db_path)

    loaded = runs.get_run(run["id"])
    replay = events.list_for_run(run["id"])
    assert loaded["status"] == "completed"
    assert [event["type"] for event in replay] == [
        "agent_status",
        "message",
        "report_section",
        "completed",
    ]
