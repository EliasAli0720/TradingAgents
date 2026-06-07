from tradingagents.dataflows import alpha_vantage_common as av


class _Response:
    text = "timestamp,close\n2026-01-01,1\n"

    def raise_for_status(self):
        return None


def test_make_api_request_sets_timeout(monkeypatch):
    captured = {}
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(av.requests, "get", fake_get)

    out = av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert "timestamp,close" in out
    assert captured["timeout"] == 30.0
    assert captured["params"]["apikey"] == "demo"


def test_make_api_request_honours_timeout_env(monkeypatch):
    captured = {}
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")
    monkeypatch.setenv("ALPHA_VANTAGE_TIMEOUT_SECONDS", "7.5")

    def fake_get(url, params, timeout):
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(av.requests, "get", fake_get)

    av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert captured["timeout"] == 7.5
