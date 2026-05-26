from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tradingagents.api.models import Session as SessionRow, User
from tradingagents.api.security import (
    generate_csrf_token,
    generate_session_id,
    hash_password,
    verify_password,
)


_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
_DUMMY_HASH = (
    "scrypt$n=16384,r=8,p=1$"
    "AAAAAAAAAAAAAAAAAAAAAA$"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


class UsernameTaken(Exception):
    pass


class InvalidUsername(Exception):
    pass


class WeakPassword(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_username(username: str) -> str:
    if not isinstance(username, str) or not _USERNAME_RE.match(username):
        raise InvalidUsername(username)
    return username.lower()


def _check_password_strength(password: str) -> None:
    if (
        not isinstance(password, str)
        or len(password) < 8
        or not re.search(r"[A-Za-z]", password)
        or not re.search(r"\d", password)
    ):
        raise WeakPassword()


class UserRepository:
    def __init__(self, db: DbSession):
        self.db = db

    def count(self) -> int:
        return self.db.scalar(select(func.count()).select_from(User)) or 0

    def get(self, user_id: str) -> Optional[User]:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> Optional[User]:
        try:
            uname = username.lower()
        except AttributeError:
            return None
        return self.db.scalar(select(User).where(User.username == uname))

    def create_user(self, username: str, password: str, role: str) -> User:
        uname = _normalize_username(username)
        _check_password_strength(password)
        if self.get_by_username(uname) is not None:
            raise UsernameTaken(uname)
        user = User(
            user_id=f"usr_{uuid4().hex}",
            username=uname,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            created_at=_utcnow(),
        )
        self.db.add(user)
        return user

    def authenticate(self, username: str, password: str) -> Optional[User]:
        user = self.get_by_username(username) if isinstance(username, str) else None
        candidate_hash = user.password_hash if user else _DUMMY_HASH
        ok = verify_password(password, candidate_hash)
        if not user or not ok or not user.is_active:
            return None
        return user

    def set_password(self, user: User, new_password: str) -> None:
        _check_password_strength(new_password)
        user.password_hash = hash_password(new_password)


class SessionRepository:
    def __init__(self, db: DbSession):
        self.db = db

    def create(
        self,
        user_id: str,
        ttl_days: int,
        user_agent: Optional[str],
        ip: Optional[str],
    ) -> tuple[str, str]:
        now = _utcnow()
        sid = generate_session_id()
        csrf = generate_csrf_token()
        self.db.add(
            SessionRow(
                session_id=sid,
                user_id=user_id,
                csrf_token=csrf,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=ttl_days),
                user_agent=((user_agent or "")[:512] or None),
                ip_text=ip,
            )
        )
        return sid, csrf

    def load_active(self, sid: str) -> Optional[SessionRow]:
        if not sid:
            return None
        row = self.db.get(SessionRow, sid)
        if row is None or row.revoked_at is not None:
            return None
        if _as_aware_utc(row.expires_at) <= _utcnow():
            return None
        return row

    def touch(self, row: SessionRow, ttl_days: int) -> None:
        now = _utcnow()
        if (now - _as_aware_utc(row.last_seen_at)).total_seconds() >= 60:
            row.last_seen_at = now
            row.expires_at = now + timedelta(days=ttl_days)

    def revoke(self, sid: str) -> None:
        row = self.db.get(SessionRow, sid)
        if row is not None and row.revoked_at is None:
            row.revoked_at = _utcnow()

    def revoke_all_for_user(
        self, user_id: str, except_sid: Optional[str] = None
    ) -> int:
        rows = (
            self.db.scalars(
                select(SessionRow).where(
                    SessionRow.user_id == user_id,
                    SessionRow.revoked_at.is_(None),
                )
            )
        ).all()
        now = _utcnow()
        count = 0
        for row in rows:
            if row.session_id == except_sid:
                continue
            row.revoked_at = now
            count += 1
        return count
