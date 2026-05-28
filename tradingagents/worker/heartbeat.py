from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread

from tradingagents.api.db import SessionLocal
from tradingagents.api.repositories import AnalysisRunRepository


@contextmanager
def heartbeat(run_id: str, interval_seconds: int) -> Iterator[None]:
    stopped = Event()

    def _beat() -> None:
        while not stopped.wait(interval_seconds):
            with SessionLocal() as session:
                repo = AnalysisRunRepository(session)
                repo.record_heartbeat(run_id)
                session.commit()

    thread = Thread(target=_beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=interval_seconds)
