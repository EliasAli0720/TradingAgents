import pytest

from tradingagents.worker.provider_limits import (
    InMemoryProviderLimiter,
    ProviderLimitExceeded,
)


def test_provider_limiter_rejects_when_concurrent_limit_reached():
    limiter = InMemoryProviderLimiter({"openai": 1})

    with limiter.acquire("openai"):
        with pytest.raises(ProviderLimitExceeded):
            with limiter.acquire("openai", wait_seconds=0):
                pass


def test_provider_limiter_releases_after_context():
    limiter = InMemoryProviderLimiter({"openai": 1})

    with limiter.acquire("openai"):
        pass

    with limiter.acquire("openai", wait_seconds=0):
        pass
