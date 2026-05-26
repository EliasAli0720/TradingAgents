# 分析 API 鉴权与多租户实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已就绪的 v1 分析 HTTP API 之上叠加常规登录 + 三角色 + owner-scoped run，实现 spec `docs/superpowers/specs/2026-05-26-analysis-api-auth-multitenancy.md`。

**Architecture:** FastAPI 浏览器 cookie session（服务端 `sessions` 表，opaque sid，无 HMAC） + double-submit CSRF cookie；scrypt 密码哈希；`AnalysisRunRepository` 加 `user_id` 过滤；worker 保留系统身份。

**Tech Stack:** FastAPI、SQLAlchemy、pydantic、`hashlib.scrypt`、Redis（沿用 Celery broker 做登录限流），pytest + FastAPI `TestClient`。

---

## File Structure

Create or modify these files:

- Modify: `tradingagents/api/models.py`
  - 新增 `User`、`Session` 模型；`AnalysisRun` 加 `user_id` 列与复合索引。
- Modify: `tradingagents/api/schemas.py`
  - 新增 register/login/change-password/me 请求/响应、`UserRole` 字面量。
- Modify: `tradingagents/api/repositories.py`
  - `AnalysisRunRepository` 加 `user_id` 默认 `None` 参数；改写 `get_run`/`get_result` 为带 owner 过滤的 `select().where(...)`。
- Modify: `tradingagents/api/deps.py`
  - 新增 `get_current_user` / `require_role` / `get_scoped_repository`。
- Modify: `tradingagents/api/app.py`
  - 注册 auth、admin 路由；挂 CSRF middleware。
- Modify: `tradingagents/api/routers/runs.py`
  - 加鉴权依赖；用 scoped repo；SSE 闭包 user_id。
- Modify: `tradingagents/api/config.py`
  - 新增 cookie / session TTL / 登录限流 / Redis URL 复用相关配置。
- Create: `tradingagents/api/security.py`
  - scrypt 密码哈希 + 校验、随机 sid / csrf token 生成。
- Create: `tradingagents/api/auth_repository.py`
  - `UserRepository`、`SessionRepository`。
- Create: `tradingagents/api/middleware.py`
  - CSRF middleware（double-submit cookie）。
- Create: `tradingagents/api/rate_limit.py`
  - Redis 滑动窗口限流（IP + username）。
- Create: `tradingagents/api/routers/auth.py`
  - `/auth/register | /auth/login | /auth/logout | /auth/me | /auth/change-password`。
- Create: `tradingagents/api/routers/admin.py`
  - `/admin/users | /admin/users/{id} | /admin/runs | /admin/users/{id}/sessions:revoke-all`。
- Create: `tests/api/test_security.py` — 密码哈希 / 校验单测。
- Create: `tests/api/test_auth_repository.py` — 用户与会话仓库测试。
- Create: `tests/api/test_auth_routes.py` — 注册/登录/登出/me/改密码端到端。
- Create: `tests/api/test_csrf.py` — CSRF middleware 行为。
- Create: `tests/api/test_runs_authz.py` — runs 路由鉴权 + owner 隔离 + role gate。
- Create: `tests/api/test_admin_routes.py` — 管理员视图与角色变更。
- Create: `tests/api/test_rate_limit.py` — 登录限流（用 fake redis 或 in-memory backend）。

不要触碰 `tradingagents/worker/`：worker 仍以系统身份调 `AnalysisRunRepository(session)`，零修改。

---

## Task 1: 用户与会话模型 + analysis_runs.user_id

**Files:**
- Modify: `tradingagents/api/models.py`
- Test: `tests/api/test_auth_repository.py`

- [ ] **Step 1: 写失败的 schema 测试**

创建 `tests/api/test_auth_repository.py`：

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base
from tradingagents.api.models import AnalysisRun, Session as SessionRow, User


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def test_user_and_session_tables_persist():
    db = _session()
    now = datetime.now(timezone.utc)
    user = User(
        user_id="usr_1",
        username="alice",
        password_hash="scrypt$...",
        role="admin",
        is_active=True,
        created_at=now,
    )
    db.add(user)
    db.add(SessionRow(
        session_id="sid_1",
        user_id="usr_1",
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=14),
    ))
    db.commit()
    assert db.get(User, "usr_1").username == "alice"
    assert db.get(SessionRow, "sid_1").user_id == "usr_1"


def test_analysis_run_has_user_id_column():
    db = _session()
    from datetime import date
    db.add(AnalysisRun(
        run_id="run_x",
        status="queued",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        user_id="usr_1",
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()
    assert db.get(AnalysisRun, "run_x").user_id == "usr_1"
```

- [ ] **Step 2: 跑 RED**

```bash
python -m pytest tests/api/test_auth_repository.py -q
```

预期失败：`User`、`Session`、`AnalysisRun.user_id` 不存在。

- [ ] **Step 3: 修改 `tradingagents/api/models.py`**

`AnalysisRun` 增加：

```python
user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

__table_args__ = (
    Index("idx_analysis_runs_created_at", "created_at"),
    Index("idx_analysis_runs_ticker_trade_date", "ticker", "trade_date"),
    Index("idx_analysis_runs_user_id_created_at", "user_id", "created_at"),
)
```

末尾追加：

```python
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    csrf_token: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_expires_at", "expires_at"),
    )
```

import 区追加 `Boolean`。

> **现有测试影响**：`AnalysisRun` 新增 NOT NULL `user_id`，原有 `tests/api/test_repositories.py` 里 `repo.create_run(...)` 会因缺 `user_id` 失败。本 Task 同时给 `AnalysisRunRepository.create_run` 加 `user_id` 默认 `"__system__"`（保持向后兼容）以保留绿色用例；Task 8 才把 `user_id` 改为必填且由路由层提供。

具体做法：在 `repositories.py` 的 `create_run` 签名末尾加 `user_id: str = "__system__"`，写入 `AnalysisRun(... user_id=user_id, ...)`。

- [ ] **Step 4: 跑 GREEN**

```bash
python -m pytest tests/api/test_auth_repository.py tests/api/test_repositories.py tests/api/test_runs_routes.py -q
```

预期：全部 PASS（含已有 33 用例 + 新 2 用例）。

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/models.py tradingagents/api/repositories.py tests/api/test_auth_repository.py
git commit -m "feat(api): add user/session models and user_id column"
```

---

## Task 2: 密码哈希 + 随机凭据

**Files:**
- Create: `tradingagents/api/security.py`
- Test: `tests/api/test_security.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from tradingagents.api.security import (
    generate_csrf_token, generate_session_id, hash_password, verify_password,
)


def test_hash_password_roundtrip():
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$")
    assert verify_password("correct horse battery", h) is True
    assert verify_password("wrong", h) is False


def test_hash_password_uses_unique_salt():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b


def test_session_and_csrf_tokens_have_expected_prefix_and_entropy():
    sid = generate_session_id()
    csrf = generate_csrf_token()
    assert sid.startswith("sid_") and len(sid) >= 36
    assert len(csrf) >= 32
    assert sid != generate_session_id()
```

- [ ] **Step 2: RED**

- [ ] **Step 3: 实现 `tradingagents/api/security.py`**

```python
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets


_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt$n={_SCRYPT_N},r={_SCRYPT_R},p={_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, params, salt_b64, digest_b64 = encoded.split("$")
        if algo != "scrypt":
            return False
        kv = dict(item.split("=") for item in params.split(","))
        n, r, p = int(kv["n"]), int(kv["r"]), int(kv["p"])
        salt = _unb64(salt_b64)
        expected = _unb64(digest_b64)
        candidate = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def generate_session_id() -> str:
    return "sid_" + secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
```

- [ ] **Step 4: GREEN**

```bash
python -m pytest tests/api/test_security.py -q
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/security.py tests/api/test_security.py
git commit -m "feat(api): add password hashing and session id generation"
```

---

## Task 3: 用户与会话仓库

**Files:**
- Create: `tradingagents/api/auth_repository.py`
- Modify: `tests/api/test_auth_repository.py`

- [ ] **Step 1: 追加失败测试**

```python
from datetime import datetime, timezone

from tradingagents.api.auth_repository import SessionRepository, UserRepository, UsernameTaken


def test_user_repository_creates_user_and_rejects_duplicate():
    db = _session()
    repo = UserRepository(db)
    user = repo.create_user(username="Alice", password="hunter22a", role="admin")
    db.commit()
    assert user.username == "alice"  # 小写归一
    assert user.role == "admin"

    import pytest
    with pytest.raises(UsernameTaken):
        repo.create_user(username="ALICE", password="other2222", role="viewer")


def test_user_repository_authenticate():
    db = _session()
    repo = UserRepository(db)
    repo.create_user(username="bob", password="hunter22a", role="viewer")
    db.commit()
    assert repo.authenticate("bob", "hunter22a") is not None
    assert repo.authenticate("bob", "WRONG") is None
    assert repo.authenticate("nobody", "hunter22a") is None


def test_session_repository_lifecycle():
    db = _session()
    users = UserRepository(db)
    sessions = SessionRepository(db)
    user = users.create_user(username="carol", password="hunter22a", role="operator")
    db.commit()

    sid, csrf = sessions.create(user_id=user.user_id, ttl_days=14, user_agent="ua", ip="1.2.3.4")
    db.commit()

    loaded = sessions.load_active(sid)
    assert loaded is not None and loaded.user_id == user.user_id and loaded.csrf_token == csrf

    sessions.revoke(sid)
    db.commit()
    assert sessions.load_active(sid) is None
```

- [ ] **Step 2: RED**

- [ ] **Step 3: 实现 `tradingagents/api/auth_repository.py`**

```python
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from tradingagents.api.models import Session as SessionRow, User
from tradingagents.api.security import (
    generate_csrf_token, generate_session_id, hash_password, verify_password,
)


_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class UsernameTaken(Exception): ...
class InvalidUsername(Exception): ...
class WeakPassword(Exception): ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(username: str) -> str:
    if not _USERNAME_RE.match(username):
        raise InvalidUsername(username)
    return username.lower()


def _check_password_strength(password: str) -> None:
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise WeakPassword()


class UserRepository:
    def __init__(self, db: DbSession):
        self.db = db

    def count(self) -> int:
        return self.db.scalar(select(func.count()).select_from(User)) or 0

    def get(self, user_id: str) -> Optional[User]:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> Optional[User]:
        return self.db.scalar(select(User).where(User.username == username.lower()))

    def create_user(self, username: str, password: str, role: str) -> User:
        uname = _normalize(username)
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
        try:
            uname = username.lower()
        except AttributeError:
            return None
        user = self.get_by_username(uname)
        # 恒定耗时：用户不存在时仍跑一次哈希
        dummy = "scrypt$n=16384,r=8,p=1$AAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        candidate_hash = user.password_hash if user else dummy
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

    def create(self, user_id: str, ttl_days: int, user_agent: str | None, ip: str | None):
        now = _utcnow()
        sid = generate_session_id()
        csrf = generate_csrf_token()
        self.db.add(SessionRow(
            session_id=sid,
            user_id=user_id,
            csrf_token=csrf,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=ttl_days),
            user_agent=(user_agent or "")[:512] or None,
            ip_text=ip,
        ))
        return sid, csrf

    def load_active(self, sid: str) -> Optional[SessionRow]:
        row = self.db.get(SessionRow, sid)
        if row is None or row.revoked_at is not None:
            return None
        if row.expires_at <= _utcnow():
            return None
        return row

    def touch(self, row: SessionRow, ttl_days: int) -> None:
        now = _utcnow()
        # 节流：距上次更新 ≥ 60s 才写库
        if (now - row.last_seen_at).total_seconds() >= 60:
            row.last_seen_at = now
            row.expires_at = now + timedelta(days=ttl_days)

    def revoke(self, sid: str) -> None:
        row = self.db.get(SessionRow, sid)
        if row and row.revoked_at is None:
            row.revoked_at = _utcnow()

    def revoke_all_for_user(self, user_id: str, except_sid: str | None = None) -> int:
        rows = self.db.scalars(select(SessionRow).where(
            SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None)
        )).all()
        count = 0
        now = _utcnow()
        for row in rows:
            if row.session_id == except_sid:
                continue
            row.revoked_at = now
            count += 1
        return count
```

- [ ] **Step 4: GREEN**

```bash
python -m pytest tests/api/test_auth_repository.py -q
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/auth_repository.py tests/api/test_auth_repository.py
git commit -m "feat(api): add user and session repositories"
```

---

## Task 4: 配置项扩展

**Files:**
- Modify: `tradingagents/api/config.py`
- Modify: `tests/api/test_config.py`

- [ ] **Step 1: 失败测试**

向 `tests/api/test_config.py` 追加：

```python
import os
from tradingagents.api.config import get_api_settings


def test_auth_defaults(monkeypatch):
    for k in [
        "TRADINGAGENTS_API_SESSION_TTL_DAYS",
        "TRADINGAGENTS_API_SESSION_COOKIE_NAME",
        "TRADINGAGENTS_API_CSRF_COOKIE_NAME",
        "TRADINGAGENTS_API_COOKIE_SECURE",
        "TRADINGAGENTS_API_LOGIN_RATE_LIMIT_PER_MIN",
    ]:
        monkeypatch.delenv(k, raising=False)
    s = get_api_settings()
    assert s.session_ttl_days == 14
    assert s.session_cookie_name == "tradingagents_session"
    assert s.csrf_cookie_name == "tradingagents_csrf"
    assert s.cookie_secure is True
    assert s.login_rate_limit_per_min == 5


def test_auth_env_overrides(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_API_COOKIE_SECURE", "false")
    monkeypatch.setenv("TRADINGAGENTS_API_SESSION_TTL_DAYS", "7")
    s = get_api_settings()
    assert s.cookie_secure is False
    assert s.session_ttl_days == 7
```

- [ ] **Step 2: RED**

- [ ] **Step 3: 实现**

`config.py` 的 `ApiSettings` 增加字段，`get_api_settings()` 读环境：

```python
session_ttl_days: int = 14
session_cookie_name: str = "tradingagents_session"
csrf_cookie_name: str = "tradingagents_csrf"
cookie_secure: bool = True
cookie_domain: str | None = None
login_rate_limit_per_min: int = 5
```

`bool` 解析用 `os.environ.get(name, "true").lower() in {"1","true","yes","on"}`。

- [ ] **Step 4: GREEN**

```bash
python -m pytest tests/api/test_config.py -q
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/config.py tests/api/test_config.py
git commit -m "build(api): add cookie/session/rate-limit settings"
```

---

## Task 5: 登录限流（Redis 滑动窗口）

**Files:**
- Create: `tradingagents/api/rate_limit.py`
- Create: `tests/api/test_rate_limit.py`

- [ ] **Step 1: 失败测试**

```python
import time
from tradingagents.api.rate_limit import InMemoryBackend, SlidingWindow


def test_sliding_window_allows_within_limit():
    w = SlidingWindow(backend=InMemoryBackend(), limit=3, window_seconds=60)
    for _ in range(3):
        assert w.allow("k") is True


def test_sliding_window_blocks_excess():
    w = SlidingWindow(backend=InMemoryBackend(), limit=3, window_seconds=60)
    for _ in range(3):
        w.allow("k")
    assert w.allow("k") is False


def test_sliding_window_recovers_after_window():
    backend = InMemoryBackend(now=lambda: 0.0)
    w = SlidingWindow(backend=backend, limit=2, window_seconds=10)
    assert w.allow("k") and w.allow("k") and not w.allow("k")
    backend.now = lambda: 11.0
    assert w.allow("k") is True
```

- [ ] **Step 2: RED**

- [ ] **Step 3: 实现**

`tradingagents/api/rate_limit.py`：抽象 `Backend` 接口（`add(key, ts)`、`count(key, since)`），内置 `InMemoryBackend`（生产用 `RedisBackend` 走 `ZADD/ZREMRANGEBYSCORE/ZCARD`，从 `REDIS_URL` 连）。`SlidingWindow.allow(key)`：

```python
class SlidingWindow:
    def __init__(self, backend, limit, window_seconds):
        self.backend, self.limit, self.window = backend, limit, window_seconds
    def allow(self, key: str) -> bool:
        now = self.backend.now()
        self.backend.add(key, now)
        return self.backend.count(key, since=now - self.window) <= self.limit
```

`RedisBackend` 仅用于生产；测试一律用 `InMemoryBackend` 注入。

- [ ] **Step 4: GREEN**

```bash
python -m pytest tests/api/test_rate_limit.py -q
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/rate_limit.py tests/api/test_rate_limit.py
git commit -m "feat(api): add sliding-window login rate limit"
```

---

## Task 6: 鉴权依赖与 scoped repo

**Files:**
- Modify: `tradingagents/api/repositories.py`
- Modify: `tradingagents/api/deps.py`

- [ ] **Step 1: 失败测试**

向 `tests/api/test_auth_repository.py` 追加：

```python
from datetime import date

from tradingagents.api.repositories import AnalysisRunRepository


def test_scoped_repository_isolates_users():
    db = _session()
    a = AnalysisRunRepository(db, user_id="usr_a")
    b = AnalysisRunRepository(db, user_id="usr_b")
    a.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    b.create_run("TSLA", date(2026, 1, 15), "stock", ["market"])
    db.commit()

    a_runs = [r.ticker for r in db.execute(
        __import__("sqlalchemy").select(__import__("tradingagents.api.models", fromlist=["AnalysisRun"]).AnalysisRun)
    ).scalars()]
    assert sorted(a_runs) == ["NVDA", "TSLA"]
    # owner 过滤
    a_run = a.create_run("AAPL", date(2026, 1, 15), "stock", ["market"]).run_id
    db.commit()
    assert b.get_run(a_run) is None  # B 看不见 A 的 run
    assert a.get_run(a_run) is not None


def test_unscoped_repository_sees_all():
    db = _session()
    a = AnalysisRunRepository(db, user_id="usr_a")
    rid = a.create_run("NVDA", date(2026, 1, 15), "stock", ["market"]).run_id
    db.commit()
    admin = AnalysisRunRepository(db)  # user_id=None
    assert admin.get_run(rid) is not None
```

- [ ] **Step 2: RED**

- [ ] **Step 3: 改 `repositories.py`**

- `__init__(self, session, user_id: str | None = None)`。
- `create_run(...)` 第一个参数照旧；末尾加 `user_id: str | None = None`；落库优先级：显式参数 > `self.user_id` > `"__system__"`。
- `get_run(run_id)`：

  ```python
  stmt = select(AnalysisRun).where(AnalysisRun.run_id == run_id)
  if self.user_id is not None:
      stmt = stmt.where(AnalysisRun.user_id == self.user_id)
  return self.session.scalar(stmt)
  ```

- `get_result(run_id)`：先 `get_run(run_id)`，None 直接返回 None；非 None 再 `self.session.get(AnalysisRunResult, run_id)`。
- `list_events(run_id, after_id)`：保持当前实现（owner 由调用方先用 `get_run` 把关）。

worker `jobs.py` 的 `AnalysisRunRepository(session)` 单参构造仍合法（user_id=None = 系统视图），无需修改。

- [ ] **Step 4: 改 `deps.py`**

新增：

```python
from fastapi import Cookie, Depends, HTTPException, Request

from tradingagents.api.auth_repository import SessionRepository, UserRepository
from tradingagents.api.config import get_api_settings
from tradingagents.api.models import User
from tradingagents.api.repositories import AnalysisRunRepository


def get_current_user(
    request: Request,
    session=Depends(get_db_session),
) -> User:
    settings = get_api_settings()
    sid = request.cookies.get(settings.session_cookie_name)
    if not sid:
        raise HTTPException(401, "authentication required")
    sessions = SessionRepository(session)
    row = sessions.load_active(sid)
    if row is None:
        raise HTTPException(401, "authentication required")
    user = UserRepository(session).get(row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "authentication required")
    sessions.touch(row, settings.session_ttl_days)
    session.commit()
    # 把 sid + csrf 暂存到 request.state 给 CSRF middleware / change-password 用
    request.state.session_row = row
    return user


def require_role(*roles: str):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "role required")
        return user
    return _check


def get_scoped_repository(
    session=Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> AnalysisRunRepository:
    user_id = None if user.role == "admin" else user.user_id
    return AnalysisRunRepository(session, user_id=user_id)
```

- [ ] **Step 5: GREEN（含已有用例）**

```bash
python -m pytest tests/api -q
```

- [ ] **Step 6: Commit**

```bash
git add tradingagents/api/repositories.py tradingagents/api/deps.py tests/api/test_auth_repository.py
git commit -m "feat(api): add scoped run repository and auth dependencies"
```

---

## Task 7: CSRF middleware

**Files:**
- Create: `tradingagents/api/middleware.py`
- Create: `tests/api/test_csrf.py`
- Modify: `tradingagents/api/app.py`

- [ ] **Step 1: 失败测试**

```python
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tradingagents.api.middleware import CsrfMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(CsrfMiddleware, csrf_cookie_name="csrf")

    @app.get("/r")
    def r(): return {"ok": True}

    @app.post("/r")
    def w(): return {"ok": True}
    return TestClient(app)


def test_get_skips_csrf():
    client = _app()
    assert client.get("/r").status_code == 200


def test_post_without_csrf_header_blocked():
    client = _app()
    client.cookies.set("csrf", "abc")
    assert client.post("/r").status_code == 403


def test_post_with_matching_csrf_allowed():
    client = _app()
    client.cookies.set("csrf", "abc")
    assert client.post("/r", headers={"X-CSRF-Token": "abc"}).status_code == 200


def test_post_without_csrf_cookie_blocked():
    client = _app()
    assert client.post("/r", headers={"X-CSRF-Token": "abc"}).status_code == 403
```

- [ ] **Step 2: RED**

- [ ] **Step 3: 实现 `middleware.py`**

```python
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CsrfMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, csrf_cookie_name: str, exempt_paths: tuple[str, ...] = ()):
        super().__init__(app)
        self.csrf_cookie_name = csrf_cookie_name
        self.exempt = exempt_paths

    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS or request.url.path in self.exempt:
            return await call_next(request)
        cookie = request.cookies.get(self.csrf_cookie_name)
        header = request.headers.get("x-csrf-token")
        if not cookie or not header or cookie != header:
            return JSONResponse({"detail": "csrf check failed"}, status_code=403)
        return await call_next(request)
```

- [ ] **Step 4: 挂到 app**

`app.py`：

```python
from tradingagents.api.config import get_api_settings
from tradingagents.api.middleware import CsrfMiddleware

settings = get_api_settings()
app.add_middleware(
    CsrfMiddleware,
    csrf_cookie_name=settings.csrf_cookie_name,
    exempt_paths=("/auth/login", "/auth/register"),
)
```

> `/auth/login` 和 `/auth/register` 必须豁免：调用方此时还没有 csrf cookie。

- [ ] **Step 5: GREEN**

```bash
python -m pytest tests/api/test_csrf.py tests/api/test_runs_routes.py -q
```

> 注意：现有 `test_runs_routes.py` 的 POST 测试将因 CSRF 失败 → 在 Task 8 改造路由层时把这些用例迁到带 cookie 的新测试。本步只验证 csrf 中间件本身。

如 `test_runs_routes.py` 暂时 RED，先记下来 Task 8 处理（标 `pytest.mark.skip` 或挪到新文件）。推荐做法：把现有 POST 路由暂时也加入 CSRF 豁免名单 `("/runs",)`，留到 Task 8 时再去掉，避免本步跨任务挂掉。

- [ ] **Step 6: Commit**

```bash
git add tradingagents/api/middleware.py tradingagents/api/app.py tests/api/test_csrf.py
git commit -m "feat(api): add csrf double-submit middleware"
```

---

## Task 8: 认证路由（register/login/logout/me/change-password）

**Files:**
- Create: `tradingagents/api/routers/auth.py`
- Modify: `tradingagents/api/app.py`
- Modify: `tradingagents/api/schemas.py`
- Create: `tests/api/test_auth_routes.py`

- [ ] **Step 1: 写 schema**

`schemas.py` 追加：

```python
UserRole = Literal["admin", "operator", "viewer"]


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: UserRole
```

- [ ] **Step 2: 失败测试**

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base
from tradingagents.api.deps import get_db_session


def _client():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    app = create_app()
    def override(): 
        with Session() as s: yield s
    app.dependency_overrides[get_db_session] = override
    return TestClient(app)


def test_first_register_becomes_admin():
    c = _client()
    r = c.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    assert r.status_code == 201
    # 二次注册成 viewer
    r2 = c.post("/auth/register", json={"username": "bob", "password": "hunter22a"})
    assert r2.status_code == 201


def test_register_rejects_weak_password():
    c = _client()
    r = c.post("/auth/register", json={"username": "x", "password": "short"})
    assert r.status_code == 422


def test_register_duplicate_username_409():
    c = _client()
    c.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    r = c.post("/auth/register", json={"username": "ALICE", "password": "hunter22a"})
    assert r.status_code == 409


def test_login_sets_cookies_and_me_returns_user():
    c = _client()
    c.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    r = c.post("/auth/login", json={"username": "alice", "password": "hunter22a"})
    assert r.status_code == 200
    assert c.cookies.get("tradingagents_session")
    assert c.cookies.get("tradingagents_csrf")

    me = c.get("/auth/me")
    assert me.status_code == 200 and me.json()["username"] == "alice" and me.json()["role"] == "admin"


def test_login_invalid_returns_same_401_for_unknown_user_and_wrong_password():
    c = _client()
    c.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    a = c.post("/auth/login", json={"username": "alice", "password": "WRONG"})
    b = c.post("/auth/login", json={"username": "nobody", "password": "whatever1"})
    assert a.status_code == 401 and b.status_code == 401
    assert a.json() == b.json()


def test_logout_invalidates_session():
    c = _client()
    c.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    c.post("/auth/login", json={"username": "alice", "password": "hunter22a"})
    csrf = c.cookies.get("tradingagents_csrf")
    r = c.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert c.get("/auth/me").status_code == 401


def test_change_password_revokes_other_sessions():
    c1 = _client()
    c1.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    c1.post("/auth/login", json={"username": "alice", "password": "hunter22a"})
    # 模拟另一终端：第二个 TestClient 共享 app/db dependency override
    # 简化：用同一 TestClient 二次登录会覆盖 cookie，跳过这一断言以保持本步聚焦
    csrf = c1.cookies.get("tradingagents_csrf")
    r = c1.post("/auth/change-password",
        json={"current_password": "hunter22a", "new_password": "hunter33b"},
        headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    # 改密后当前 session 仍可用
    assert c1.get("/auth/me").status_code == 200
```

> 多 session 吊销的全场景测试放到独立用例文件，便于用两个独立 `TestClient` 共享同一 engine（参考 `test_admin_routes.py` 写法，本步先验证单端逻辑）。

- [ ] **Step 3: 实现 `routers/auth.py`**

要点：

- `POST /auth/register`：`UserRepository.create_user`；表内为空 → 角色 `admin`，否则 `viewer`。
- `POST /auth/login`：限流先行（`Depends(get_login_rate_limiter)`）；`UserRepository.authenticate`；成功 → 调 `SessionRepository.create` 写 sid+csrf；通过 `response.set_cookie` 下发两个 cookie；返回 `UserResponse`。
- `POST /auth/logout`：读 `request.state.session_row.session_id` → revoke；`response.delete_cookie(...)`。
- `GET /auth/me`：直接返回 `Depends(get_current_user)` 的 user。
- `POST /auth/change-password`：校验旧密码，`set_password`，调 `revoke_all_for_user(user.user_id, except_sid=current_sid)`。

cookie 下发样板：

```python
response.set_cookie(
    settings.session_cookie_name, sid,
    httponly=True, secure=settings.cookie_secure, samesite="lax",
    max_age=settings.session_ttl_days * 86400, path="/",
    domain=settings.cookie_domain,
)
response.set_cookie(
    settings.csrf_cookie_name, csrf,
    httponly=False, secure=settings.cookie_secure, samesite="lax",
    max_age=settings.session_ttl_days * 86400, path="/",
    domain=settings.cookie_domain,
)
```

错误处理：
- 弱密码 → `422`（Pydantic 在 schema 里用 `field_validator` 转换为 ValidationError）。
- 用户名重复 → `409`。
- 登录失败 → `401 {"detail":"invalid credentials"}`，**总是** `time.sleep` 到固定下限（如已走 `verify_password` 恒定耗时即可，无需额外 sleep）。
- 限流命中 → `429`，附 `Retry-After: 60`。

`app.py` `include_router(auth.router)`。

- [ ] **Step 4: GREEN**

```bash
python -m pytest tests/api/test_auth_routes.py -q
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/routers/auth.py tradingagents/api/app.py tradingagents/api/schemas.py tests/api/test_auth_routes.py
git commit -m "feat(api): add auth routes (register/login/logout/me/change-password)"
```

---

## Task 9: runs 路由鉴权 + owner 隔离

**Files:**
- Modify: `tradingagents/api/routers/runs.py`
- Modify: `tradingagents/api/middleware.py`（去掉 `/runs` CSRF 豁免）
- Modify: `tests/api/test_runs_routes.py`
- Create: `tests/api/test_runs_authz.py`

- [ ] **Step 1: 失败测试**

`test_runs_authz.py`：

```python
# 通过 register → login 拿到 cookies；分别构造 admin/operator/viewer 三个 client。
# 断言：
# - 无 cookie 调 POST /runs → 401
# - viewer 调 POST /runs → 403
# - operator 调 POST /runs → 202
# - operator A 不能 GET operator B 的 run → 404
# - admin 可以 GET 任意用户的 run → 200
# - operator 调 POST /runs 缺 X-CSRF-Token → 403
```

详细写法参考 Task 8 的 `_client()` 工具；新增一个辅助 `_login_as(c, username, password)`，把 csrf 写进默认 headers。

- [ ] **Step 2: RED**

- [ ] **Step 3: 改 `routers/runs.py`**

- 所有 `POST` / `GET /runs/*` 加 `Depends(get_current_user)`。
- `POST /runs` 加 `Depends(require_role("admin","operator"))`，并把 `repo` 改为 `Depends(get_scoped_repository)`；`create_run` 调用补 `user_id=current_user.user_id`。
- `GET /runs/{id}` / `/result` / `/events` 改为 `Depends(get_scoped_repository)`；admin role 在 deps 层自动获得无过滤 repo。
- `stream_events` 把 `current_user` 与 `get_scoped_repository` 一起注入；将 `user_id` 闭包进 generator；generator 内每次 `stream_session_factory()` 重新构造 `AnalysisRunRepository(stream_session, user_id=...)`。

- [ ] **Step 4: 调整 `test_runs_routes.py`**

原有用例改为：建一个 fixture 自动注册 + 登录一个 admin，把 csrf header 注入到 TestClient 默认 headers。无需重写断言。

- [ ] **Step 5: 去掉 `/runs` 的 CSRF 豁免**

`app.py` 的 `exempt_paths` 改回 `("/auth/login", "/auth/register")`。

- [ ] **Step 6: GREEN**

```bash
python -m pytest tests/api -q
```

确认现有 33 用例 + 新 authz 用例全绿。

- [ ] **Step 7: Commit**

```bash
git add tradingagents/api/routers/runs.py tradingagents/api/app.py tests/api/test_runs_routes.py tests/api/test_runs_authz.py
git commit -m "feat(api): enforce auth and owner scoping on runs routes"
```

---

## Task 10: Admin 路由

**Files:**
- Create: `tradingagents/api/routers/admin.py`
- Modify: `tradingagents/api/schemas.py`
- Modify: `tradingagents/api/app.py`
- Create: `tests/api/test_admin_routes.py`

- [ ] **Step 1: 失败测试**

- `GET /admin/users` admin 可访 → 200；operator 不可 → 403。
- `PATCH /admin/users/{id}` 修改 role 成功。
- `GET /admin/runs?user_id=` 跨用户能看到。
- `POST /admin/users/{id}/sessions:revoke-all` 后该用户的 cookie 再次 `GET /auth/me` → 401。

- [ ] **Step 2: RED**

- [ ] **Step 3: 实现 `routers/admin.py`**

四个 endpoint，全部 `Depends(require_role("admin"))`。`GET /admin/runs` 直接复用未 scoped 的 `AnalysisRunRepository(session)`（不传 user_id），按可选参数过滤；`PATCH` 用 Pydantic 部分更新模型 `AdminUserPatch(role?, is_active?)`。

- [ ] **Step 4: GREEN**

```bash
python -m pytest tests/api/test_admin_routes.py -q
```

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/routers/admin.py tradingagents/api/schemas.py tradingagents/api/app.py tests/api/test_admin_routes.py
git commit -m "feat(api): add admin routes"
```

---

## Task 11: 登录限流接入

**Files:**
- Modify: `tradingagents/api/routers/auth.py`
- Modify: `tradingagents/api/deps.py`
- Modify: `tests/api/test_auth_routes.py`

- [ ] **Step 1: 失败测试**

```python
def test_login_rate_limit_hits_429():
    c = _client_with_in_memory_limiter(limit=3)
    c.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    for _ in range(3):
        c.post("/auth/login", json={"username": "alice", "password": "WRONG"})
    r = c.post("/auth/login", json={"username": "alice", "password": "WRONG"})
    assert r.status_code == 429 and r.headers.get("Retry-After")
```

- [ ] **Step 2: RED**

- [ ] **Step 3: 实现**

`deps.py` 增加 `get_login_rate_limiter()`：

```python
_login_limiter_singleton = None

def get_login_rate_limiter() -> SlidingWindow:
    global _login_limiter_singleton
    if _login_limiter_singleton is None:
        s = get_api_settings()
        backend = RedisBackend(s.redis_url) if s.redis_url else InMemoryBackend()
        _login_limiter_singleton = SlidingWindow(
            backend=backend, limit=s.login_rate_limit_per_min, window_seconds=60,
        )
    return _login_limiter_singleton
```

`/auth/login` 改：

```python
def login(req: LoginRequest, request: Request,
          limiter: SlidingWindow = Depends(get_login_rate_limiter),
          ...):
    key = f"login:{request.client.host}:{req.username.lower()}"
    if not limiter.allow(key):
        raise HTTPException(429, "too many attempts", headers={"Retry-After": "60"})
    ...
```

测试用 `app.dependency_overrides[get_login_rate_limiter]` 注入 `SlidingWindow(InMemoryBackend(), limit=3, window_seconds=60)`。

- [ ] **Step 4: GREEN**

- [ ] **Step 5: Commit**

```bash
git add tradingagents/api/routers/auth.py tradingagents/api/deps.py tests/api/test_auth_routes.py
git commit -m "feat(api): rate-limit login attempts"
```

---

## Task 12: E2E 验证与文档

**Files:**
- 可能 Modify: `docs/superpowers/specs/2026-05-26-analysis-api-auth-multitenancy.md`（仅在实现与 spec 出现偏离时）。
- 可能 Modify: `RUNNING.md`（新增 cookie/HTTPS 部署注意项）。

- [ ] **Step 1: 跑全套 API/worker 测试**

```bash
python -m pytest tests/api tests/worker -q
```

预期：全部 PASS。原有 33 + 新增 ≥ 30 ≈ 60+ 用例。

- [ ] **Step 2: 跑全仓 pytest**

```bash
python -m pytest tests -q
```

记录任何被外部 provider 凭据卡住的失败，确认与本次改动无关。

- [ ] **Step 3: 编译检查**

```bash
python -m compileall -q tradingagents tradingbot cli tests
```

- [ ] **Step 4: 冒烟 import**

```bash
python - <<'PY'
from tradingagents.api.app import app
print([r.path for r in app.routes if hasattr(r, "path")])
PY
```

输出包含 `/auth/register`、`/auth/login`、`/auth/logout`、`/auth/me`、`/auth/change-password`、`/admin/users`、`/runs`、`/runs/{run_id}`、`/runs/{run_id}/result`、`/runs/{run_id}/events`、`/health`。

- [ ] **Step 5: 文档补丁（可选）**

如果开发期决定 `COOKIE_SECURE=false`，在 `RUNNING.md` 部署章节加一行：生产必须 HTTPS + `TRADINGAGENTS_API_COOKIE_SECURE=true`。

- [ ] **Step 6: 最终 commit**

```bash
git add RUNNING.md  # 如有
git commit -m "docs: document auth deployment requirements" || true
```

---

## Execution Notes

- 任务严格 test-first：每个 Task 必须先 RED 再 GREEN。
- 不要 patch worker：worker 用 `AnalysisRunRepository(session)` 单参 = 系统视图，零修改。
- 不要在测试里调用真实 LLM / Provider。
- 历史 `__system__` 数据不在本次实现里处理（spec 留作 v2 admin 工具）。
- CSRF 豁免名单严格控制：只豁免 `/auth/login` 与 `/auth/register`。Task 7 临时豁免 `/runs` 必须在 Task 9 移除。
- session 滑动过期写库节流（60s）确保高频请求不打爆 DB；测试用例不要依赖具体 throttle 周期，只断言行为。
- 登录失败响应必须**完全相同**（用户不存在 vs 密码错），用 `verify_password` 对 dummy hash 跑一次保证恒定耗时。
- 越权访问他人 run 一律 404，不要 403。
- Cookie 必须 `HttpOnly`（session）+ `non-HttpOnly`（csrf），生产 `Secure; SameSite=Lax`。
- 不实现 token / Bearer 通道，不实现密码找回，不集成 `tradingbot/auth/`。
- 不要在日志输出 cookie 或密码字段。
- 实现时所有现有测试必须保持绿色；如本任务步骤会暂时让某用例 RED，**必须**在同一 Task 内修复。
