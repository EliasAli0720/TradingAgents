from types import SimpleNamespace

import pytest

from tradingagents.graph.checkpointer import run_thread_id
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.worker.cancellation import AnalysisCancelled, CancellationToken


def test_run_thread_id_uses_run_id():
    assert run_thread_id("run_abc") == "run_abc"


def test_trading_graph_raise_if_cancelled_delegates_to_context_token():
    calls = []
    graph = object.__new__(TradingAgentsGraph)
    graph.context = SimpleNamespace(
        cancellation_token=SimpleNamespace(
            raise_if_cancelled=lambda: calls.append("checked")
        )
    )

    graph._raise_if_cancelled()

    assert calls == ["checked"]


def test_trading_graph_raise_if_cancelled_allows_missing_token():
    graph = object.__new__(TradingAgentsGraph)
    graph.context = None

    graph._raise_if_cancelled()


def test_graph_setup_cancellable_stops_before_node_execution():
    setup = object.__new__(GraphSetup)
    setup.cancellation_token = CancellationToken(lambda: True)
    executed = []

    wrapped = setup._cancellable("Node", lambda state: executed.append(state))

    with pytest.raises(AnalysisCancelled):
        wrapped({"x": 1})

    assert executed == []


def test_run_graph_stream_checks_cancellation_before_section_callback():
    checks = []
    callbacks = []

    def raise_on_pre_callback_check():
        checks.append("checked")
        if len(checks) == 3:
            raise AnalysisCancelled()

    graph = object.__new__(TradingAgentsGraph)
    graph.debug = False
    graph.context = SimpleNamespace(
        cancellation_token=SimpleNamespace(
            raise_if_cancelled=raise_on_pre_callback_check
        )
    )
    graph.config = {"checkpoint_enabled": False}
    graph.memory_log = SimpleNamespace(get_past_context=lambda ticker: [])
    graph.propagator = SimpleNamespace(
        create_initial_state=lambda *args, **kwargs: {"initial": "state"},
        get_graph_args=lambda: {},
    )
    graph.graph = SimpleNamespace(
        stream=lambda *args, **kwargs: iter(
            [{"market_report": "body", "final_trade_decision": "Hold"}]
        )
    )

    with pytest.raises(AnalysisCancelled):
        graph._run_graph(
            "AAPL",
            "2024-01-02",
            on_section_ready=lambda key, value: callbacks.append((key, value)),
        )

    assert checks == ["checked", "checked", "checked"]
    assert callbacks == []
