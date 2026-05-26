from __future__ import annotations

import json
from typing import Any


REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
)


def extract_reports(final_state: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe(final_state.get(key, "")) for key in REPORT_KEYS}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(v) for v in value]
        return str(value)


def json_safe_state(final_state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe(value)
        for key, value in final_state.items()
        if key != "messages"
    }
