from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from tradingagents.api.models import AnalysisRun


logger = logging.getLogger(__name__)


class AnalysisCancelled(Exception):
    pass


class CancellationToken:
    def __init__(self, is_cancelled: Callable[[], bool]):
        self._is_cancelled = is_cancelled

    def raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise AnalysisCancelled()


def build_db_cancellation_token(
    session_factory: Callable[[], Any],
    run_id: str,
) -> CancellationToken:
    def is_cancelled() -> bool:
        try:
            with session_factory() as session:
                run = session.get(AnalysisRun, run_id)
                return run is None or run.status in {"cancelling", "cancelled"}
        except Exception:
            logger.warning(
                "cancellation status check failed for run %s",
                run_id,
                exc_info=True,
            )
            return False

    return CancellationToken(is_cancelled)
