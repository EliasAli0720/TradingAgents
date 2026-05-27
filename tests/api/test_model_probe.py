from tradingagents.api.model_probe import classify_probe_exception


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
