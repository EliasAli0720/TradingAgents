from __future__ import annotations

from collections.abc import Callable


class AnalysisCancelled(Exception):
    pass


class CancellationToken:
    def __init__(self, is_cancelled: Callable[[], bool]):
        self._is_cancelled = is_cancelled

    def raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise AnalysisCancelled()
