from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from typing import Protocol


class Backend(Protocol):
    def now(self) -> float: ...
    def add(self, key: str, timestamp: float) -> None: ...
    def count(self, key: str, since: float) -> int: ...


class InMemoryBackend:
    def __init__(self, now: Callable[[], float] | None = None):
        self.now = now or time.time
        self._events: dict[str, list[float]] = defaultdict(list)

    def add(self, key: str, timestamp: float) -> None:
        self._events[key].append(timestamp)

    def count(self, key: str, since: float) -> int:
        bucket = self._events.get(key)
        if not bucket:
            return 0
        # Prune old entries opportunistically.
        bucket[:] = [ts for ts in bucket if ts >= since]
        return len(bucket)


class RedisBackend:
    """Redis sliding-window backend using sorted sets."""

    def __init__(self, redis_url: str, namespace: str = "tradingagents:rl"):
        import redis  # local import so tests don't need a redis server

        self._client = redis.Redis.from_url(redis_url)
        self._ns = namespace

    def now(self) -> float:
        return time.time()

    def _key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    def add(self, key: str, timestamp: float) -> None:
        member = f"{timestamp:.6f}:{id(self)}"
        self._client.zadd(self._key(key), {member: timestamp})

    def count(self, key: str, since: float) -> int:
        full_key = self._key(key)
        self._client.zremrangebyscore(full_key, 0, since - 1e-9)
        return int(self._client.zcard(full_key))


class SlidingWindow:
    def __init__(self, backend: Backend, limit: int, window_seconds: float):
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.backend = backend
        self.limit = limit
        self.window = window_seconds

    def allow(self, key: str) -> bool:
        now = self.backend.now()
        self.backend.add(key, now)
        return self.backend.count(key, since=now - self.window) <= self.limit
