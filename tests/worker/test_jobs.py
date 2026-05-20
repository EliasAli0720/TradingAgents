from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import RunEventRepository, RunRepository
from tradingagents.worker.analysis import run_analysis_with_graph
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


class FakeGraph:
    def __init__(self):
        self.graph = self

    def stream(self, state, **kwargs):
        yield {"market_report": "Market report", "messages": []}
        yield {"final_trade_decision": "Rating: Buy", "messages": []}


class FakePropagator:
    def create_initial_state(self, ticker, analysis_date, asset_type="stock"):
        return {"company_of_interest": ticker, "trade_date": analysis_date, "asset_type": asset_type}

    def get_graph_args(self, callbacks=None):
        return {}


def test_analysis_adapter_streams_graph_chunks(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.create_run(
        "SPY",
        "2026-05-19",
        "stock",
        {"ticker": "SPY", "analysis_date": "2026-05-19", "asset_type": "stock"},
    )
    graph = FakeGraph()
    graph.propagator = FakePropagator()

    run_analysis_with_graph(run["id"], db_path, graph)

    loaded = runs.get_run(run["id"])
    replay = events.list_for_run(run["id"])
    assert loaded["status"] == "completed"
    assert any(event["type"] == "report_section" for event in replay)
    assert replay[-1]["type"] == "completed"
