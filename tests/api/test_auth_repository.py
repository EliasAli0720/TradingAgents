from datetime import date, datetime, timedelta, timezone

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
        password_hash="scrypt$placeholder",
        role="admin",
        is_active=True,
        created_at=now,
    )
    db.add(user)
    db.add(
        SessionRow(
            session_id="sid_1",
            user_id="usr_1",
            csrf_token="csrf_1",
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=14),
        )
    )
    db.commit()
    assert db.get(User, "usr_1").username == "alice"
    loaded = db.get(SessionRow, "sid_1")
    assert loaded.user_id == "usr_1"
    assert loaded.csrf_token == "csrf_1"
    assert loaded.revoked_at is None


def test_analysis_run_has_user_id_column():
    db = _session()
    db.add(
        AnalysisRun(
            run_id="run_x",
            status="queued",
            ticker="NVDA",
            trade_date=date(2026, 1, 15),
            asset_type="stock",
            analysts=["market"],
            user_id="usr_1",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    assert db.get(AnalysisRun, "run_x").user_id == "usr_1"


# --- UserRepository / SessionRepository ----------------------------------


def test_user_repository_creates_user_and_rejects_duplicate():
    import pytest

    from tradingagents.api.auth_repository import (
        InvalidUsername,
        UserRepository,
        UsernameTaken,
        WeakPassword,
    )

    db = _session()
    repo = UserRepository(db)
    user = repo.create_user(username="Alice", password="hunter22a", role="admin")
    db.commit()
    assert user.username == "alice"
    assert user.role == "admin"

    with pytest.raises(UsernameTaken):
        repo.create_user(username="ALICE", password="other22b", role="viewer")

    with pytest.raises(InvalidUsername):
        repo.create_user(username="ab", password="hunter22a", role="viewer")

    with pytest.raises(WeakPassword):
        repo.create_user(username="charlie", password="short", role="viewer")


def test_user_repository_authenticate():
    from tradingagents.api.auth_repository import UserRepository

    db = _session()
    repo = UserRepository(db)
    repo.create_user(username="bob", password="hunter22a", role="viewer")
    db.commit()

    user = repo.authenticate("BOB", "hunter22a")
    assert user is not None and user.username == "bob"
    assert repo.authenticate("bob", "WRONG") is None
    assert repo.authenticate("nobody", "hunter22a") is None


def test_user_repository_inactive_user_cannot_authenticate():
    from tradingagents.api.auth_repository import UserRepository

    db = _session()
    repo = UserRepository(db)
    user = repo.create_user(username="dora", password="hunter22a", role="viewer")
    user.is_active = False
    db.commit()
    assert repo.authenticate("dora", "hunter22a") is None


def test_user_repository_count_and_get_by_username():
    from tradingagents.api.auth_repository import UserRepository

    db = _session()
    repo = UserRepository(db)
    assert repo.count() == 0
    repo.create_user(username="alice", password="hunter22a", role="admin")
    repo.create_user(username="bob", password="hunter22a", role="viewer")
    db.commit()
    assert repo.count() == 2
    assert repo.get_by_username("ALICE").role == "admin"
    assert repo.get_by_username("missing") is None


def test_session_repository_lifecycle():
    from tradingagents.api.auth_repository import SessionRepository, UserRepository

    db = _session()
    users = UserRepository(db)
    sessions = SessionRepository(db)
    user = users.create_user(username="carol", password="hunter22a", role="operator")
    db.commit()

    sid, csrf = sessions.create(
        user_id=user.user_id, ttl_days=14, user_agent="ua-1", ip="1.2.3.4"
    )
    db.commit()

    loaded = sessions.load_active(sid)
    assert loaded is not None
    assert loaded.user_id == user.user_id
    assert loaded.csrf_token == csrf

    sessions.revoke(sid)
    db.commit()
    assert sessions.load_active(sid) is None


def test_session_repository_expired_session_not_loaded():
    from datetime import timedelta

    from tradingagents.api.auth_repository import SessionRepository, UserRepository

    db = _session()
    users = UserRepository(db)
    sessions = SessionRepository(db)
    user = users.create_user(username="eden", password="hunter22a", role="viewer")
    db.commit()
    sid, _csrf = sessions.create(user_id=user.user_id, ttl_days=14, user_agent=None, ip=None)
    db.commit()

    row = db.get(SessionRow, sid)
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert sessions.load_active(sid) is None


def test_session_repository_revoke_all_for_user_except():
    from tradingagents.api.auth_repository import SessionRepository, UserRepository

    db = _session()
    users = UserRepository(db)
    sessions = SessionRepository(db)
    user = users.create_user(username="fay", password="hunter22a", role="viewer")
    db.commit()

    keep_sid, _ = sessions.create(user.user_id, ttl_days=14, user_agent=None, ip=None)
    drop_a, _ = sessions.create(user.user_id, ttl_days=14, user_agent=None, ip=None)
    drop_b, _ = sessions.create(user.user_id, ttl_days=14, user_agent=None, ip=None)
    db.commit()

    revoked = sessions.revoke_all_for_user(user.user_id, except_sid=keep_sid)
    db.commit()
    assert revoked == 2
    assert sessions.load_active(keep_sid) is not None
    assert sessions.load_active(drop_a) is None
    assert sessions.load_active(drop_b) is None
