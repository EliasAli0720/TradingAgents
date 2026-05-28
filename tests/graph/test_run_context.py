from tradingagents.graph.checkpointer import run_thread_id


def test_run_thread_id_uses_run_id():
    assert run_thread_id("run_abc") == "run_abc"
