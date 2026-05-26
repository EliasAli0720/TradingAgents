import json
from datetime import date

from tradingagents.api.serialization import extract_reports, json_safe_state


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
