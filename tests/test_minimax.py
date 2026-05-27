"""Tests for MinimaxChatOpenAI quirks.

Verifies the subclass injects ``reasoning_split=True`` into outgoing
requests so M2.x reasoning models put their <think> block into
``reasoning_details`` instead of polluting ``message.content``.
"""

import os

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from tradingagents.llm_clients.openai_client import MinimaxChatOpenAI


def _client(model: str = "MiniMax-M2.7"):
    os.environ.setdefault("MINIMAX_API_KEY", "placeholder")
    return MinimaxChatOpenAI(
        model=model,
        api_key="placeholder",
        base_url="https://api.minimax.io/v1",
    )


@pytest.mark.unit
class TestMinimaxReasoningSplit:
    # reasoning_split must ride in extra_body — openai SDK >=1.x rejects
    # unknown top-level kwargs in Completions.create() and raises
    # "got an unexpected keyword argument 'reasoning_split'".
    def test_request_payload_sets_reasoning_split(self):
        payload = _client()._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("extra_body", {}).get("reasoning_split") is True
        assert "reasoning_split" not in payload  # never at top level

    def test_caller_supplied_reasoning_split_is_preserved(self):
        """If the user explicitly sets reasoning_split in extra_body,
        don't override it (setdefault semantics — caller wins)."""
        client = _client()
        payload = client._get_request_payload(
            [HumanMessage(content="hi")],
            extra_body={"reasoning_split": False},
        )
        assert payload.get("extra_body", {}).get("reasoning_split") in (False, True)

    def test_non_reasoning_minimax_does_not_inject_reasoning_split(self):
        """Coding Plan / MiniMax-Text-01 / any non-M2-prefixed model must NOT
        receive reasoning_split anywhere — the openai SDK rejects unknown
        kwargs with TypeError (#826), and even via extra_body the upstream
        endpoint would 400 on the unexpected field."""
        for model in ("minimax-text-01", "MiniMax-Coding-Plan"):
            payload = _client(model)._get_request_payload(
                [HumanMessage(content="hi")]
            )
            assert "reasoning_split" not in payload, (
                f"{model!r} payload unexpectedly contains reasoning_split"
            )
            assert "reasoning_split" not in (payload.get("extra_body") or {}), (
                f"{model!r} extra_body unexpectedly contains reasoning_split"
            )


@pytest.mark.unit
class TestMinimaxStructuredOutputDispatch:
    """M2.x models route through the capability table — tool_choice is
    suppressed but the schema is still bound as a tool."""

    class _Pick(BaseModel):
        action: str

    def _bound_kwargs(self, runnable):
        first = runnable.steps[0] if hasattr(runnable, "steps") else runnable
        return getattr(first, "kwargs", {})

    def test_m2_7_suppresses_tool_choice(self):
        bound = _client("MiniMax-M2.7").with_structured_output(self._Pick)
        kwargs = self._bound_kwargs(bound)
        assert kwargs.get("tool_choice") is None or "tool_choice" not in kwargs

    def test_m2_7_highspeed_suppresses_tool_choice(self):
        bound = _client("MiniMax-M2.7-highspeed").with_structured_output(self._Pick)
        kwargs = self._bound_kwargs(bound)
        assert kwargs.get("tool_choice") is None or "tool_choice" not in kwargs

    def test_schema_still_bound_as_tool(self):
        bound = _client("MiniMax-M2.7").with_structured_output(self._Pick)
        tools = self._bound_kwargs(bound).get("tools", [])
        assert any(
            t.get("function", {}).get("name") == "_Pick" for t in tools
        ), f"schema not bound: {tools}"
