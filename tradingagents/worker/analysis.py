from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from tradingagents.api.serialization import extract_reports, json_safe_state
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def run_tradingagents_analysis(
    ticker: str,
    trade_date: date,
    asset_type: str,
    analysts: list[str],
    llm_config: dict[str, Any],
) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    config.update(
        {
            "llm_provider": llm_config["llm_provider"],
            "deep_think_llm": llm_config["deep_think_llm"],
            "quick_think_llm": llm_config["quick_think_llm"],
            "backend_url": llm_config.get("backend_url"),
        }
    )
    graph = TradingAgentsGraph(selected_analysts=analysts, config=config)
    final_state, decision = graph.propagate(
        ticker,
        trade_date.isoformat(),
        asset_type=asset_type,
    )
    return {
        "decision": decision,
        "reports": extract_reports(final_state),
        "final_state": json_safe_state(final_state),
    }
