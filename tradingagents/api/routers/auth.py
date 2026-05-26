from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from tradingagents.api.auth_repository import (
    InvalidUsername,
    SessionRepository,
    UserRepository,
    UsernameTaken,
    WeakPassword,
)
from tradingagents.api.config import get_api_settings
from tradingagents.api.deps import (
    get_current_user,
    get_db_session,
    get_login_rate_limiter,
)
from tradingagents.api.models import User
from tradingagents.api.rate_limit import SlidingWindow
from tradingagents.api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)


router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, sid: str, csrf: str) -> None:
    settings = get_api_settings()
    max_age = settings.session_ttl_days * 86400
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sid,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )


def _clear_auth_cookies(response: Response) -> None:
    settings = get_api_settings()
    response.delete_cookie(settings.session_cookie_name, path="/", domain=settings.cookie_domain)
    response.delete_cookie(settings.csrf_cookie_name, path="/", domain=settings.cookie_domain)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(request: RegisterRequest, session: Session = Depends(get_db_session)):
    users = UserRepository(session)
    role = "admin" if users.count() == 0 else "viewer"
    try:
        user = users.create_user(
            username=request.username, password=request.password, role=role
        )
    except UsernameTaken:
        raise HTTPException(status_code=409, detail="username taken")
    except InvalidUsername:
        raise HTTPException(status_code=422, detail="invalid username")
    except WeakPassword:
        raise HTTPException(status_code=422, detail="password too weak")
    session.commit()
    return UserResponse(user_id=user.user_id, username=user.username, role=user.role)


@router.post("/login", response_model=UserResponse)
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_db_session),
    limiter: SlidingWindow = Depends(get_login_rate_limiter),
):
    client_ip = request.client.host if request.client else "unknown"
    username_lc = body.username.lower() if isinstance(body.username, str) else "_"
    if not limiter.allow(f"login:{client_ip}:{username_lc}"):
        raise HTTPException(
            status_code=429,
            detail="too many attempts",
            headers={"Retry-After": "60"},
        )
    users = UserRepository(session)
    user = users.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials")

    settings = get_api_settings()
    sessions = SessionRepository(session)
    sid, csrf = sessions.create(
        user_id=user.user_id,
        ttl_days=settings.session_ttl_days,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    user.last_login_at = datetime.now(timezone.utc)
    session.commit()

    _set_auth_cookies(response, sid, csrf)
    return UserResponse(user_id=user.user_id, username=user.username, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    request: Request,
    session: Session = Depends(get_db_session),
    _user: User = Depends(get_current_user),
):
    row = getattr(request.state, "session_row", None)
    if row is not None:
        SessionRepository(session).revoke(row.session_id)
        session.commit()
    _clear_auth_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse(user_id=user.user_id, username=user.username, role=user.role)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    users = UserRepository(session)
    if users.authenticate(user.username, body.current_password) is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    try:
        users.set_password(user, body.new_password)
    except WeakPassword:
        raise HTTPException(status_code=422, detail="password too weak")

    current_sid = getattr(getattr(request.state, "session_row", None), "session_id", None)
    SessionRepository(session).revoke_all_for_user(user.user_id, except_sid=current_sid)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
