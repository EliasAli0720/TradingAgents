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
