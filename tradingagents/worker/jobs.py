from __future__ import annotations

from tradingagents.api.repositories import RunEventRepository, RunRepository


def run_fake_analysis(run_id: str, db_path: str) -> None:
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    runs.update_status(run_id, "running")
    events.append(run_id, "agent_status", {"agent": "Market Analyst", "status": "running"})
    events.append(run_id, "message", {"type": "System", "content": "Fake analysis started"})
    events.append(
        run_id,
        "report_section",
        {"section": "market_report", "content": "Fake market report for local development."},
    )
    runs.update_status(run_id, "completed", result={"final_trade_decision": "Rating: Hold"})
    events.append(run_id, "completed", {"signal": "Hold"})


def run_tradingagents_analysis(run_id: str, db_path: str) -> None:
    from tradingagents.api.repositories import RunRepository
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.worker.analysis import run_analysis_with_graph

    runs = RunRepository(db_path)
    run = runs.get_run(run_id)
    config = DEFAULT_CONFIG.copy()
    run_config = run["config"]
    config["llm_provider"] = run_config["llm_provider"]
    config["quick_think_llm"] = run_config["quick_think_llm"]
    config["deep_think_llm"] = run_config["deep_think_llm"]
    config["output_language"] = run_config.get("output_language", "English")
    config["checkpoint_enabled"] = run_config.get("checkpoint_enabled", False)
    config["max_debate_rounds"] = run_config.get("research_depth", 1)
    config["max_risk_discuss_rounds"] = run_config.get("research_depth", 1)

    graph = TradingAgentsGraph(
        selected_analysts=run_config["analysts"],
        config=config,
        debug=False,
    )
    run_analysis_with_graph(run_id, db_path, graph)
