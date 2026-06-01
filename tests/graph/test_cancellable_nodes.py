"""Regression tests for GraphSetup._cancellable.

A cancellation token wraps every graph node. Tool nodes are LangGraph Runnables
(e.g. ToolNode) that are NOT directly callable and must be driven via .invoke —
calling them like fn(state) raised "'ToolNode' object is not callable" and broke
every worker run that routed through a tool node.
"""

from tradingagents.graph.setup import GraphSetup


class _FakeToken:
    def raise_if_cancelled(self) -> None:  # no-op token
        pass


class _NotCallableRunnable:
    """Mimics ToolNode: exposes .invoke, is not directly callable."""

    def __init__(self) -> None:
        self.invoked_with = None

    def invoke(self, state):
        self.invoked_with = state
        return {"ok": True}


def _setup(token):
    return GraphSetup(
        quick_thinking_llm=None,
        deep_thinking_llm=None,
        tool_nodes={},
        conditional_logic=None,
        cancellation_token=token,
    )


def test_cancellable_invokes_runnable_nodes():
    runnable = _NotCallableRunnable()
    assert not callable(runnable)  # like ToolNode

    wrapped = _setup(_FakeToken())._cancellable("market_tools", runnable)
    result = wrapped({"messages": []})

    assert result == {"ok": True}
    assert runnable.invoked_with == {"messages": []}


def test_cancellable_calls_plain_function_nodes():
    seen = {}

    def fn(state):
        seen["state"] = state
        return "done"

    wrapped = _setup(_FakeToken())._cancellable("agent", fn)
    assert wrapped({"y": 2}) == "done"
    assert seen["state"] == {"y": 2}


def test_cancellable_passes_through_without_token():
    def fn(state):
        return state

    # No token → node is returned unchanged (LangGraph drives it itself).
    assert _setup(None)._cancellable("agent", fn) is fn
