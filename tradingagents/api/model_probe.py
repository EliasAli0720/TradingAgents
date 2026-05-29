from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tradingagents.llm_clients.factory import create_llm_client


ModelProbeStatus = Literal[
    "success",
    "invalid_api_key",
    "model_not_found",
    "endpoint_unreachable",
    "permission_denied",
    "timeout",
    "provider_error",
]


@dataclass(frozen=True)
class ModelProbeRequest:
    provider: str
    model: str
    backend_url: str | None
    api_key: str | None
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class ModelProbeResult:
    status: ModelProbeStatus
    message: str


def probe_model(request: ModelProbeRequest) -> ModelProbeResult:
    """Run a low-cost LLM call to verify that the configured model is usable."""
    try:
        client = create_llm_client(
            request.provider,
            request.model,
            request.backend_url,
            api_key=request.api_key,
            timeout=request.timeout_seconds,
            max_retries=0,
        )
        llm = client.get_llm()
        response = llm.invoke(
            "Reply with exactly one lowercase word: pong",
            config={"run_name": "model_settings_live_probe"},
        )
        content = str(getattr(response, "content", response)).strip().lower()
        if "pong" not in content:
            excerpt = content.replace("\n", " ")[:160] or "<empty>"
            return ModelProbeResult(
                status="provider_error",
                message=(
                    "model responded, but did not return the expected probe text: "
                    f"{excerpt}"
                ),
            )
        return ModelProbeResult(status="success", message="probe returned pong")
    except Exception as exc:  # noqa: BLE001 - provider SDKs expose inconsistent errors.
        return classify_probe_exception(exc)


def classify_probe_exception(exc: Exception) -> ModelProbeResult:
    """Map provider-specific exceptions into stable API-facing categories."""
    text = str(exc).lower()
    class_name = exc.__class__.__name__.lower()
    combined = f"{class_name} {text}"

    if "timeout" in combined or "timed out" in combined:
        return ModelProbeResult(status="timeout", message=_safe_message(exc))

    if (
        "model_not_found" in combined
        or "model not found" in combined
        or "model was not found" in combined
        or "does not exist" in combined
        or ("404" in combined and "model" in combined)
    ):
        return ModelProbeResult(status="model_not_found", message=_safe_message(exc))

    if (
        "invalid api key" in combined
        or "incorrect api key" in combined
        or "authentication" in combined
        or "unauthorized" in combined
        or "401" in combined
    ):
        return ModelProbeResult(status="invalid_api_key", message=_safe_message(exc))

    if (
        "permission" in combined
        or "forbidden" in combined
        or "access denied" in combined
        or "403" in combined
    ):
        return ModelProbeResult(status="permission_denied", message=_safe_message(exc))

    if (
        "connect" in class_name
        or "connection" in combined
        or "network" in combined
        or "name resolution" in combined
        or "nodename nor servname" in combined
        or "connection refused" in combined
        or "failed to establish" in combined
    ):
        return ModelProbeResult(status="endpoint_unreachable", message=_safe_message(exc))

    return ModelProbeResult(status="provider_error", message=_safe_message(exc))


def _safe_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__
