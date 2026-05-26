from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.auth_repository import SessionRepository
from tradingagents.api.deps import get_db_session, require_role
from tradingagents.api.models import AnalysisRun, User
from tradingagents.api.schemas import (
    AdminUserPatch,
    AdminUserResponse,
    RunStatusResponse,
)


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    session: Session = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
):
    users = session.scalars(select(User).order_by(User.created_at.asc())).all()
    return [
        AdminUserResponse(
            user_id=u.user_id,
            username=u.username,
            role=u.role,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def patch_user(
    user_id: str,
    patch: AdminUserPatch,
    session: Session = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if patch.role is not None:
        user.role = patch.role
    if patch.is_active is not None:
        user.is_active = patch.is_active
    session.commit()
    return AdminUserResponse(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
    )


@router.post(
    "/users/{user_id}/sessions:revoke-all",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_all_sessions(
    user_id: str,
    session: Session = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
):
    if session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    SessionRepository(session).revoke_all_for_user(user_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs", response_model=list[RunStatusResponse])
def list_runs(
    user_id: str | None = None,
    status_filter: str | None = None,
    session: Session = Depends(get_db_session),
    _admin: User = Depends(require_role("admin")),
):
    stmt = select(AnalysisRun).order_by(AnalysisRun.created_at.desc())
    if user_id is not None:
        stmt = stmt.where(AnalysisRun.user_id == user_id)
    if status_filter is not None:
        stmt = stmt.where(AnalysisRun.status == status_filter)
    runs = session.scalars(stmt).all()
    return runs
