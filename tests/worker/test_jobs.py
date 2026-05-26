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
