"""Report translation.

The English analysis reports are the source of truth. After a run succeeds,
its reports can be translated into other languages and stored alongside the
English originals. The translator is pluggable: the first implementation uses
the user's own configured LLM; swapping in a dedicated translation API later
only means adding another implementation and changing the factory.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


LANGUAGE_NAMES = {
    "zh": "Simplified Chinese (简体中文)",
    "en": "English",
}

_PROMPT_TEMPLATE = (
    "You are a professional financial translator. Translate the following "
    "Markdown analysis report into {language}.\n\n"
    "Strict rules:\n"
    "- Preserve ALL Markdown structure exactly: headings, tables, lists, "
    "bold/italic, code blocks, horizontal rules.\n"
    "- Do NOT translate or alter: numbers, percentages, currency amounts, "
    "ticker symbols, and technical indicator abbreviations (MACD, RSI, EPS, "
    "SMA, EMA, ATR, VWMA, P/E, etc.).\n"
    "- Keep the meaning faithful; do not add, drop, or reorder sections.\n"
    "- Output ONLY the translated Markdown. No preamble, no explanation.\n\n"
    "----- BEGIN REPORT -----\n{markdown}\n----- END REPORT -----"
)


class ReportTranslator(Protocol):
    def translate(self, markdown: str, *, target_lang: str) -> str: ...


class LLMReportTranslator:
    """Translate using the user's own configured (quick) model."""

    def __init__(self, llm: Any):
        # `llm` is anything with `.invoke(prompt) -> response` (langchain
        # chat model). Injected so tests can pass a fake.
        self._llm = llm

    def translate(self, markdown: str, *, target_lang: str) -> str:
        if not markdown or not markdown.strip():
            return markdown
        language = LANGUAGE_NAMES.get(target_lang, target_lang)
        prompt = _PROMPT_TEMPLATE.format(language=language, markdown=markdown)
        response = self._llm.invoke(
            prompt,
            config={"run_name": "report_translation"},
        )
        content = getattr(response, "content", response)
        return str(content).strip()


def translate_reports(
    reports: dict[str, str],
    *,
    target_lang: str,
    translator: ReportTranslator,
) -> dict[str, str]:
    """Translate each report section independently.

    Per-section (not whole-report) translation keeps each LLM call under the
    provider output-token cap (e.g. MiniMax CN's 2048) and lets a single
    section failure fall back to English rather than failing everything.
    """
    translated: dict[str, str] = {}
    for key, text in reports.items():
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            translated[key] = translator.translate(text, target_lang=target_lang)
        except Exception:  # noqa: BLE001 - one section failing must not abort the rest
            logger.warning("translation failed for report section %s", key, exc_info=True)
            # Skip: caller/clients fall back to the English original for this key.
            continue
    return translated


def build_llm_translator(llm_config: dict[str, Any]) -> LLMReportTranslator:
    """Build the default LLM-backed translator from a run's llm_config snapshot.

    Uses the quick-think model (translation is mechanical and cost-sensitive).
    """
    from tradingagents.api.crypto import decrypt_secret
    from tradingagents.llm_clients.factory import create_llm_client

    api_key = None
    if llm_config.get("api_key_encrypted"):
        api_key = decrypt_secret(llm_config["api_key_encrypted"])

    client = create_llm_client(
        llm_config["llm_provider"],
        llm_config["quick_think_llm"],
        llm_config.get("backend_url"),
        api_key=api_key,
        max_retries=1,
    )
    return LLMReportTranslator(client.get_llm())
