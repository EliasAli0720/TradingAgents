from tradingagents.api.model_probe import classify_probe_exception, probe_model, ModelProbeRequest


def test_classify_probe_exception_distinguishes_expected_failure_types():
    cases = [
        (TimeoutError("request timed out"), "timeout"),
        (RuntimeError("invalid API key provided"), "invalid_api_key"),
        (RuntimeError("model was not found by provider"), "model_not_found"),
        (PermissionError("403 forbidden"), "permission_denied"),
        (ConnectionError("connection refused"), "endpoint_unreachable"),
        (RuntimeError("upstream returned malformed payload"), "provider_error"),
    ]

    for exc, expected_status in cases:
        result = classify_probe_exception(exc)

        assert result.status == expected_status
        assert result.message


def test_probe_model_reports_unexpected_response_excerpt(monkeypatch):
    class _LLM:
        def invoke(self, prompt, config=None):
            class _Response:
                content = "hello instead"

            return _Response()

    class _Client:
        def get_llm(self):
            return _LLM()

    monkeypatch.setattr(
        "tradingagents.api.model_probe.create_llm_client",
        lambda *args, **kwargs: _Client(),
    )

    result = probe_model(
        ModelProbeRequest(
            provider="google",
            model="gemini-2.5-flash-lite",
            backend_url=None,
            api_key="key",
        )
    )

    assert result.status == "provider_error"
    assert "hello instead" in result.message
