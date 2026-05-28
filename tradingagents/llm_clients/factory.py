from typing import Any, Optional

from .base_client import BaseLLMClient
from tradingagents.worker.provider_limits import ProviderLimiter

# Providers that use the OpenAI-compatible chat completions API
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek",
    "qwen", "qwen-cn",
    "glm", "glm-cn",
    "minimax", "minimax-cn",
    "ollama", "openrouter",
)


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Provider modules are imported lazily so that simply importing this
    factory (e.g. during test collection) does not pull in heavy LLM SDKs
    or fail when their API keys are absent.

    Args:
        provider: LLM provider name
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()
    provider_limiter = kwargs.pop("provider_limiter", None)

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return _with_provider_limiter(
            OpenAIClient(model, base_url, provider=provider_lower, **kwargs),
            provider_lower,
            provider_limiter,
        )

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return _with_provider_limiter(
            AnthropicClient(model, base_url, **kwargs),
            provider_lower,
            provider_limiter,
        )

    if provider_lower == "google":
        from .google_client import GoogleClient
        return _with_provider_limiter(
            GoogleClient(model, base_url, **kwargs),
            provider_lower,
            provider_limiter,
        )

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return _with_provider_limiter(
            AzureOpenAIClient(model, base_url, **kwargs),
            provider_lower,
            provider_limiter,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")


def _with_provider_limiter(
    client: BaseLLMClient,
    provider: str,
    provider_limiter: ProviderLimiter | None,
) -> BaseLLMClient:
    if provider_limiter is None:
        return client
    return _LimitedLLMClient(client, provider, provider_limiter)


class _LimitedLLMClient(BaseLLMClient):
    def __init__(self, inner: BaseLLMClient, provider: str, limiter: ProviderLimiter):
        self._inner = inner
        self._provider = provider
        self._limiter = limiter
        super().__init__(inner.model, inner.base_url, **inner.kwargs)

    def get_llm(self) -> Any:
        return _LimitedLLM(self._inner.get_llm(), self._provider, self._limiter)

    def validate_model(self) -> bool:
        return self._inner.validate_model()

    def get_provider_name(self) -> str:
        return self._inner.get_provider_name()

    def warn_if_unknown_model(self) -> None:
        self._inner.warn_if_unknown_model()


class _LimitedLLM:
    def __init__(self, inner: Any, provider: str, limiter: ProviderLimiter):
        self._inner = inner
        self._provider = provider
        self._limiter = limiter

    def invoke(self, *args, **kwargs):
        with self._limiter.acquire(self._provider):
            return self._inner.invoke(*args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        with self._limiter.acquire(self._provider):
            return await self._inner.ainvoke(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
