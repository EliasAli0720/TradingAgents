from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from threading import Condition
from time import monotonic


class ProviderLimitExceeded(RuntimeError):
    pass


class ProviderLimiter:
    @contextmanager
    def acquire(self, provider: str, wait_seconds: float = 30) -> Iterator[None]:
        yield


class InMemoryProviderLimiter(ProviderLimiter):
    def __init__(self, limits: dict[str, int]):
        self._limits = {provider.lower(): limit for provider, limit in limits.items()}
        self._active: dict[str, int] = {}
        self._condition = Condition()

    @contextmanager
    def acquire(self, provider: str, wait_seconds: float = 30) -> Iterator[None]:
        provider_key = provider.lower()
        limit = self._limits.get(provider_key)
        if limit is None or limit <= 0:
            with nullcontext():
                yield
            return

        deadline = monotonic() + wait_seconds
        with self._condition:
            while self._active.get(provider_key, 0) >= limit:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise ProviderLimitExceeded(f"provider limit reached: {provider_key}")
                self._condition.wait(remaining)
            self._active[provider_key] = self._active.get(provider_key, 0) + 1

        try:
            yield
        finally:
            with self._condition:
                current = self._active.get(provider_key, 0)
                if current <= 1:
                    self._active.pop(provider_key, None)
                else:
                    self._active[provider_key] = current - 1
                self._condition.notify_all()


class RedisProviderLimiter(ProviderLimiter):
    def __init__(self, redis_client, limits: dict[str, int], *, key_prefix: str = "provider_limit"):
        self._redis = redis_client
        self._limits = {provider.lower(): limit for provider, limit in limits.items()}
        self._key_prefix = key_prefix

    @classmethod
    def from_url(
        cls,
        redis_url: str,
        limits: dict[str, int],
        *,
        key_prefix: str = "provider_limit",
    ) -> "RedisProviderLimiter":
        import redis

        return cls(redis.Redis.from_url(redis_url), limits, key_prefix=key_prefix)

    @contextmanager
    def acquire(self, provider: str, wait_seconds: float = 30) -> Iterator[None]:
        provider_key = provider.lower()
        limit = self._limits.get(provider_key)
        if limit is None or limit <= 0:
            with nullcontext():
                yield
            return

        key = f"{self._key_prefix}:{provider_key}"
        deadline = monotonic() + wait_seconds
        acquired = False
        while not acquired:
            count = int(self._redis.incr(key))
            if count == 1:
                self._redis.expire(key, max(int(wait_seconds) + 60, 60))
            if count <= limit:
                acquired = True
                break
            self._redis.decr(key)
            if wait_seconds <= 0 or monotonic() >= deadline:
                raise ProviderLimitExceeded(f"provider limit reached: {provider_key}")

        try:
            yield
        finally:
            count = int(self._redis.decr(key))
            if count <= 0:
                self._redis.delete(key)
