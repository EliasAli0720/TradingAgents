from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal



PROMPT_VERSION = "stock-recommendations-v1"
_TICKER_RE = re.compile(r"^[A-Z0-9._\-^]{1,32}$")


_ALLOWED_SOURCES = {"watchlist", "model_expansion"}


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
    """Parse the model output leniently: take whatever valid items we can and
    skip/repair the rest, rather than discarding the whole batch when a single
    item is malformed (a wrong ``source`` value, missing field, bad priority).
    """
    payload = _extract_json_object(raw)
    items = payload.get("recommendations") if payload else None
    if not isinstance(items, list):
        return []

    candidates: list[RecommendationCandidate] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).strip().upper()
        if not _TICKER_RE.fullmatch(ticker) or ticker in seen:
            continue
        seen.add(ticker)

        # Models occasionally invent a source ("market", "expansion", …) — treat
        # anything unknown as a broad-market pick instead of dropping the item.
        source = str(item.get("source", "")).strip().lower()
        if source not in _ALLOWED_SOURCES:
            source = "model_expansion"

        try:
            priority = int(item.get("priority", index + 1))
        except (TypeError, ValueError):
            priority = index + 1
        if priority < 1:
            priority = index + 1

        candidates.append(
            RecommendationCandidate(
                ticker=ticker,
                source=source,  # type: ignore[arg-type]
                priority=priority,
                reason=str(item.get("reason", "") or "").strip(),
                risk=str(item.get("risk", "") or "").strip(),
            )
        )

    return candidates


def _extract_json_object(raw: str) -> dict | None:
    """Pull the recommendations JSON object out of arbitrary model text.

    Tolerates Markdown code fences, ``<think>`` reasoning blocks, and prose
    around the JSON: scans for the first balanced ``{...}`` that parses and
    contains a ``recommendations`` key (``json.raw_decode`` handles braces inside
    strings correctly, unlike a naive first-brace/last-brace slice).
    """
    if not raw:
        return None
    text = re.sub(r"<think>.*?</think>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    decoder = json.JSONDecoder()
    idx = 0
    while True:
        start = text.find("{", idx)
        if start == -1:
            return None
        try:
            obj, _end = decoder.raw_decode(text, start)
        except ValueError:
            idx = start + 1
            continue
        if isinstance(obj, dict) and "recommendations" in obj:
            return obj
        idx = start + 1


_LANGUAGE_NAMES = {
    "zh": "Simplified Chinese (简体中文)",
    "zh-cn": "Simplified Chinese (简体中文)",
    "en": "English",
    "en-us": "English",
}


def _language_instruction(language: str | None) -> str:
    """Tell the model which language to write reason/risk in (tickers stay as
    symbols). Empty string for unknown/unset languages → default English."""
    if not language:
        return ""
    name = _LANGUAGE_NAMES.get(language.strip().lower())
    if name is None:
        return ""
    return f'Write the "reason" and "risk" fields in {name}; keep ticker symbols unchanged.'


class RecommendationGenerator:
    def __init__(self, llm: Any):
        self.llm = llm

    def generate(
        self,
        watchlist: list[str],
        recent_context: list[dict[str, Any]],
        today: date,
        language: str | None = None,
    ) -> list[RecommendationCandidate]:
        has_watchlist = bool(watchlist)
        system = (
            "You are generating stock pre-analysis triage candidates. "
            "Return valid JSON only with a recommendations array. "
            "Recommend exactly 5 tickers when possible. "
            + (
                'Prefer stocks from the provided watchlist, but you may include '
                'source="model_expansion" candidates when they are useful. '
                if has_watchlist
                else "The watchlist is empty, so recommend across the broad market: "
                "pick the most compelling, liquid, widely-traded stocks you would "
                'flag for pre-analysis today, and mark every candidate source="model_expansion". '
            )
            + "Do not claim that full analysis has already happened; only explain "
            "why each ticker may deserve pre-analysis. "
            + _language_instruction(language)
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
