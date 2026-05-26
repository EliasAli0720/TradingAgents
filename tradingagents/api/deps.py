from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from tradingagents.api.auth_repository import SessionRepository, UserRepository
from tradingagents.api.config import get_api_settings
from tradingagents.api.db import SessionLocal, get_session
from tradingagents.api.models import User
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.worker.jobs import run_analysis_task


def get_db_session() -> Iterator[Session]:
    yield from get_session()


def enqueue_analysis_task(run_id: str) -> str:
    result = run_analysis_task.delay(run_id)
    return result.id


def get_task_enqueue() -> Callable[[str], str]:
    return enqueue_analysis_task


def get_stream_session_factory():
    return SessionLocal


def get_current_user(
    request: Request,
    session: Session = Depends(get_db_session),
) -> User:
    settings = get_api_settings()
    sid = request.cookies.get(settings.session_cookie_name)
    if not sid:
        raise HTTPException(status_code=401, detail="authentication required")

    sessions = SessionRepository(session)
    row = sessions.load_active(sid)
    if row is None:
        raise HTTPException(status_code=401, detail="authentication required")

    user = UserRepository(session).get(row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="authentication required")

    sessions.touch(row, settings.session_ttl_days)
    session.commit()

    # Attach session row for downstream code (logout, change-password, CSRF audit).
    request.state.session_row = row
    return user


def require_role(*roles: str):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="role required")
        return user

    return _check


def get_scoped_repository(
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> AnalysisRunRepository:
    user_id = None if user.role == "admin" else user.user_id
    return AnalysisRunRepository(session, user_id=user_id)
