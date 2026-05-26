from tradingagents.api.rate_limit import InMemoryBackend, SlidingWindow


def test_sliding_window_allows_within_limit():
    window = SlidingWindow(backend=InMemoryBackend(), limit=3, window_seconds=60)
    for _ in range(3):
        assert window.allow("k") is True


def test_sliding_window_blocks_excess():
    window = SlidingWindow(backend=InMemoryBackend(), limit=3, window_seconds=60)
    for _ in range(3):
        assert window.allow("k") is True
    assert window.allow("k") is False
    assert window.allow("k") is False


def test_sliding_window_isolates_keys():
    window = SlidingWindow(backend=InMemoryBackend(), limit=1, window_seconds=60)
    assert window.allow("a") is True
    assert window.allow("a") is False
    assert window.allow("b") is True


def test_sliding_window_recovers_after_window():
    fake_time = {"now": 0.0}
    backend = InMemoryBackend(now=lambda: fake_time["now"])
    window = SlidingWindow(backend=backend, limit=2, window_seconds=10)
    assert window.allow("k") is True
    assert window.allow("k") is True
    assert window.allow("k") is False
    fake_time["now"] = 11.0
    assert window.allow("k") is True
