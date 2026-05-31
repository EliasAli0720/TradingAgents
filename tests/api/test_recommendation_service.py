import json
from datetime import date

from tradingagents.api.recommendation_service import (
    RecommendationCandidate,
    RecommendationGenerator,
    parse_recommendations,
)


def _item(
    ticker: str,
    *,
    source: str = "watchlist",
    priority: int = 1,
    reason: str | None = None,
    risk: str | None = None,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "source": source,
        "priority": priority,
        "reason": reason if reason is not None else f" {ticker} reason ",
        "risk": risk if risk is not None else f" {ticker} risk ",
    }


def test_parse_recommendations_normalizes_filters_and_deduplicates_tickers():
    raw = json.dumps(
        {
            "recommendations": [
                _item("nvda", priority=2),
                _item("../BAD", priority=1),
                _item("NVDA", priority=3),
                _item(
                    " brk.b ",
                    source="model_expansion",
                    priority=4,
                    reason=" BRK candidate ",
                    risk=" Liquidity ",
                ),
                _item(
                    "^gspc",
                    source="model_expansion",
                    priority=5,
                    reason=" Index signal ",
                    risk=" Macro ",
                ),
            ]
        }
    )

    candidates = parse_recommendations(raw)

    assert candidates == [
        RecommendationCandidate(
            ticker="NVDA",
            source="watchlist",
            priority=2,
            reason="nvda reason",
            risk="nvda risk",
        ),
        RecommendationCandidate(
            ticker="BRK.B",
            source="model_expansion",
            priority=4,
            reason="BRK candidate",
            risk="Liquidity",
        ),
        RecommendationCandidate(
            ticker="^GSPC",
            source="model_expansion",
            priority=5,
            reason="Index signal",
            risk="Macro",
        ),
    ]


def test_parse_recommendations_extracts_json_object_from_model_text():
    raw = (
        "Here is the JSON:\n"
        + json.dumps({"recommendations": [_item("msft", priority=1)]})
        + "\nDone."
    )

    candidates = parse_recommendations(raw)

    assert [candidate.ticker for candidate in candidates] == ["MSFT"]


def test_recommendation_generator_builds_prompt_and_returns_candidates():
    response_payload = {
        "recommendations": [
            _item("aapl", priority=1, reason="Catalyst", risk="Valuation")
        ]
    }

    class FakeResponse:
        content = [{"type": "text", "text": json.dumps(response_payload)}]

    class FakeLLM:
        def __init__(self):
            self.messages = None

        def invoke(self, messages):
            self.messages = messages
            return FakeResponse()

    llm = FakeLLM()
    recent_context = [
        {
            "ticker": "NVDA",
            "trade_date": "2026-05-30",
            "decision": "Hold",
        }
    ]

    candidates = RecommendationGenerator(llm).generate(
        watchlist=["NVDA", "AAPL"],
        recent_context=recent_context,
        today=date(2026, 5, 31),
    )

    assert candidates == [
        RecommendationCandidate(
            ticker="AAPL",
            source="watchlist",
            priority=1,
            reason="Catalyst",
            risk="Valuation",
        )
    ]
    assert llm.messages is not None
    assert llm.messages[0][0] == "system"
    assert llm.messages[1][0] == "human"
    human_payload = json.loads(llm.messages[1][1])
    assert "schema" in human_payload
    assert "response_schema_example" not in human_payload
    prompt_text = "\n".join(message for _, message in llm.messages)
    assert "2026-05-31" in prompt_text
    assert "NVDA" in prompt_text
    assert "AAPL" in prompt_text
    assert "recent_analysis_context" in prompt_text
    assert "Hold" in prompt_text
