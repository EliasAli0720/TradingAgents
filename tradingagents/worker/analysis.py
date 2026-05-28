from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from tradingagents.api.artifacts import LocalArtifactStore
from tradingagents.api.crypto import decrypt_secret
from tradingagents.api.serialization import extract_reports, json_safe_state
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reports import save_analysis_report


def run_tradingagents_analysis(
    ticker: str,
    trade_date: date,
    asset_type: str,
    analysts: list[str],
    llm_config: dict[str, Any],
    *,
    run_id: str | None = None,
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
    if llm_config.get("api_key_encrypted"):
        config["api_key"] = decrypt_secret(llm_config["api_key_encrypted"])
    graph = TradingAgentsGraph(selected_analysts=analysts, config=config)
    final_state, decision = graph.propagate(
        ticker,
        trade_date.isoformat(),
        asset_type=asset_type,
    )
    artifacts = []
    if run_id is None:
        save_analysis_report(final_state, ticker, config["reports_dir"])
    else:
        artifacts = save_analysis_report(
            final_state,
            ticker,
            config["reports_dir"],
            run_id=run_id,
            artifact_store=LocalArtifactStore(config["reports_dir"]),
        )
    output = {
        "decision": decision,
        "reports": extract_reports(final_state),
        "final_state": json_safe_state(final_state),
    }
    if artifacts:
        output["artifacts"] = artifacts
    return output
