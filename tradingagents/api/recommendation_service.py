from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


PROMPT_VERSION = "stock-recommendations-v1"
_TICKER_RE = re.compile(r"^[A-Z0-9._\-^]{1,32}$")


class _RecommendationItem(BaseModel):
    ticker: str
    source: Literal["watchlist", "model_expansion"]
    priority: int = Field(ge=1)
    reason: str
    risk: str


class _RecommendationResponse(BaseModel):
    recommendations: list[_RecommendationItem]


@dataclass(frozen=True)
class RecommendationCandidate:
    ticker: str
    source: Literal["watchlist", "model_expansion"]
    priority: int
    reason: str
    risk: str


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    return _content_to_text(content)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_content_to_text(item) for item in content)
    if isinstance(content, dict):
        if "text" in content:
            return _content_to_text(content["text"])
        if "content" in content:
            return _content_to_text(content["content"])
        return ""

    text = getattr(content, "text", None)
    if text is not None:
        return _content_to_text(text)

    nested_content = getattr(content, "content", None)
    if nested_content is not None:
        return _content_to_text(nested_content)

    return str(content)


def parse_recommendations(raw: str) -> list[RecommendationCandidate]:
    response = _parse_response(raw)
    if response is None:
        return []

    candidates: list[RecommendationCandidate] = []
    seen: set[str] = set()
    for item in response.recommendations:
        ticker = item.ticker.strip().upper()
        if not _TICKER_RE.fullmatch(ticker):
            continue
        if ticker in seen:
            continue

        seen.add(ticker)
        candidates.append(
            RecommendationCandidate(
                ticker=ticker,
                source=item.source,
                priority=item.priority,
                reason=item.reason.strip(),
                risk=item.risk.strip(),
            )
        )

    return candidates


def _parse_response(raw: str) -> _RecommendationResponse | None:
    try:
        return _RecommendationResponse.model_validate_json(raw)
    except (ValidationError, ValueError):
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        payload = json.loads(raw[start : end + 1])
        return _RecommendationResponse.model_validate(payload)
    except (ValidationError, ValueError, TypeError):
        return None


class RecommendationGenerator:
    def __init__(self, llm: Any):
        self.llm = llm

    def generate(
        self,
        watchlist: list[str],
        recent_context: list[dict[str, Any]],
        today: date,
    ) -> list[RecommendationCandidate]:
        system = (
            "You are generating stock pre-analysis triage candidates. "
            "Return valid JSON only with a recommendations array. "
            "Recommend exactly 5 tickers when possible. "
            "Prefer stocks from the provided watchlist, but you may include "
            'source="model_expansion" candidates when they are useful. '
            "Do not claim that full analysis has already happened; only explain "
            "why each ticker may deserve pre-analysis."
        )
        user = {
            "date": today.isoformat(),
            "watchlist": list(watchlist),
            "recent_analysis_context": list(recent_context),
            "schema": {
                "recommendations": [
                    {
                        "ticker": "AAPL",
                        "source": "watchlist",
                        "priority": 1,
                        "reason": "Short reason for pre-analysis triage.",
                        "risk": "Short risk to consider before analysis.",
                    }
                ]
            },
        }
        response = self.llm.invoke(
            [("system", system), ("human", json.dumps(user, ensure_ascii=False))]
        )
        return parse_recommendations(_message_content(response))
