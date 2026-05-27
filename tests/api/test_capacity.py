from datetime import date

from sqlalchemy.orm import sessionmaker

from tradingagents.api.capacity import CapacityConfig, capacity_snapshot
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.repositories import AnalysisRunRepository
from tradingagents.api.routers.runs import _user_capacity_lock_stmt


def test_capacity_snapshot_counts_active_and_user_backlog():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        usr_1 = AnalysisRunRepository(session, user_id="usr_1")
        for _ in range(3):
            run = usr_1.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
            run.status = "running"
        for _ in range(2):
            usr_1.create_run("AAPL", date(2026, 1, 15), "stock", ["market"])

        usr_2 = AnalysisRunRepository(session, user_id="usr_2")
        run = usr_2.create_run("TSLA", date(2026, 1, 15), "stock", ["market"])
        run.status = "dispatching"
        session.commit()

        snapshot = capacity_snapshot(
            session,
            "usr_1",
            CapacityConfig(system_running=100, user_running=5, user_backlog=50),
        )

    assert snapshot.system_active == 4
    assert snapshot.user_active == 3
    assert snapshot.user_backlog == 5
    assert snapshot.can_create is True


def test_user_capacity_lock_stmt_uses_postgresql_row_lock():
    from sqlalchemy.dialects import postgresql

    compiled = str(
        _user_capacity_lock_stmt("usr_1").compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "FROM users" in compiled
    assert "users.user_id = 'usr_1'" in compiled
    assert "FOR UPDATE" in compiled
