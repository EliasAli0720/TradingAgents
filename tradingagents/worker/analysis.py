from __future__ import annotations

from tradingagents.api.repositories import RunEventRepository, RunRepository
from tradingagents.graph.signal_processing import SignalProcessor

REPORT_KEYS = {
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
}


def run_analysis_with_graph(run_id: str, db_path: str, graph) -> None:
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    run = runs.get_run(run_id)
    config = run["config"]
    ticker = config.get("ticker", run["ticker"])
    analysis_date = config.get("analysis_date", run["analysis_date"])
    asset_type = config.get("asset_type", run["asset_type"])

    runs.update_status(run_id, "running")
    events.append(run_id, "message", {"type": "System", "content": f"Analyzing {ticker} on {analysis_date}"})

    init_state = graph.propagator.create_initial_state(ticker, analysis_date, asset_type=asset_type)
    args = graph.propagator.get_graph_args()

    final_state = {}
    for chunk in graph.graph.stream(init_state, **args):
        final_state.update(chunk)
        for key in REPORT_KEYS:
            if chunk.get(key):
                events.append(run_id, "report_section", {"section": key, "content": chunk[key]})

    decision = final_state.get("final_trade_decision", "")
    signal = SignalProcessor().process_signal(decision)
    runs.update_status(run_id, "completed", result={"signal": signal, "final_trade_decision": decision})
    events.append(run_id, "completed", {"signal": signal})
