from __future__ import annotations

from collections.abc import Callable, Iterator

from sqlalchemy.orm import Session

from tradingagents.api.db import get_session
from tradingagents.worker.jobs import run_analysis_task


def get_db_session() -> Iterator[Session]:
    yield from get_session()


def enqueue_analysis_task(run_id: str) -> str:
    result = run_analysis_task.delay(run_id)
    return result.id


def get_task_enqueue() -> Callable[[str], str]:
    return enqueue_analysis_task
