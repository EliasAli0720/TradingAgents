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
