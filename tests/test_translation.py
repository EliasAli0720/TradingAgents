import pytest

from tradingagents.translation import (
    LLMReportTranslator,
    translate_reports,
)


class _FakeLLM:
    def __init__(self, mapping=None, fail_on=None):
        self.mapping = mapping or {}
        self.fail_on = fail_on or set()
        self.calls = []

    def invoke(self, prompt, config=None):
        self.calls.append(prompt)
        for trigger in self.fail_on:
            if trigger in prompt:
                raise RuntimeError("provider error")

        class _Resp:
            content = "[translated]"

        return _Resp()


@pytest.mark.unit
def test_llm_translator_skips_empty_text():
    llm = _FakeLLM()
    out = LLMReportTranslator(llm).translate("   ", target_lang="zh")
    assert out == "   "
    assert llm.calls == []


@pytest.mark.unit
def test_llm_translator_returns_model_content():
    llm = _FakeLLM()
    out = LLMReportTranslator(llm).translate("## Market\nbody", target_lang="zh")
    assert out == "[translated]"
    assert "Simplified Chinese" in llm.calls[0]
    assert "## Market" in llm.calls[0]


@pytest.mark.unit
def test_translate_reports_skips_empty_and_non_string_sections():
    llm = _FakeLLM()
    translator = LLMReportTranslator(llm)
    out = translate_reports(
        {
            "market_report": "real content",
            "news_report": "",
            "fundamentals_report": 123,  # type: ignore[dict-item]
        },
        target_lang="zh",
        translator=translator,
    )
    assert set(out.keys()) == {"market_report"}
    assert out["market_report"] == "[translated]"


@pytest.mark.unit
def test_translate_reports_swallows_single_section_failure():
    # One section's failure must not abort the rest; it just falls out of the map.
    llm = _FakeLLM(fail_on={"news content"})
    translator = LLMReportTranslator(llm)
    out = translate_reports(
        {
            "market_report": "market content",
            "news_report": "news content",
        },
        target_lang="zh",
        translator=translator,
    )
    assert set(out.keys()) == {"market_report"}
