from datetime import date, datetime, timedelta, timezone
from threading import Thread

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from tradingagents.api.db import Base, create_db_engine, ensure_additive_schema
from tradingagents.api.models import (
    AnalysisRun,
    AnalysisMemoryEntry,
    AnalysisRunEvent,
    AnalysisRunArtifact,
    AnalysisRunResult,
    User,
    UserModelSetting,
)
from tradingagents.api.repositories import AnalysisRunRepository, utcnow


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def test_analysis_run_postgresql_schema_has_capacity_server_defaults():
    ddl = str(CreateTable(AnalysisRun.__table__).compile(dialect=postgresql.dialect()))

    assert "priority INTEGER DEFAULT 0 NOT NULL" in ddl
    assert "attempt_count INTEGER DEFAULT 0 NOT NULL" in ddl
    assert "max_attempts INTEGER DEFAULT 2 NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL" in ddl


def test_analysis_tables_can_store_run_event_and_result():
    session = _session()
    now = datetime.now(timezone.utc)
    run = AnalysisRun(
        run_id="run_test",
        status="queued",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market", "news"],
        user_id="__system__",
        current_step=None,
        celery_task_id=None,
        error=None,
        created_at=now,
    )
    session.add(run)
    session.add(
        AnalysisRunEvent(
            run_id="run_test",
            event_type="run_queued",
            payload={"run_id": "run_test", "status": "queued"},
            created_at=now,
        )
    )
    session.add(
        AnalysisRunResult(
            run_id="run_test",
            decision="Hold",
            reports={"final_trade_decision": "Rating: Hold"},
            final_state={"company_of_interest": "NVDA"},
            created_at=now,
        )
    )
    session.commit()

    saved = session.get(AnalysisRun, "run_test")
    assert saved.ticker == "NVDA"
    assert saved.analysts == ["market", "news"]
    assert session.query(AnalysisRunEvent).one().event_type == "run_queued"
    assert session.get(AnalysisRunResult, "run_test").decision == "Hold"


def test_create_db_engine_enforces_sqlite_foreign_keys():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()

    session.add(
        AnalysisRunEvent(
            run_id="missing_run",
            event_type="run_queued",
            payload={"run_id": "missing_run", "status": "queued"},
            created_at=datetime.now(timezone.utc),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_create_db_engine_shares_in_memory_sqlite_across_threaded_sessions():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    now = datetime.now(timezone.utc)

    with Session() as session:
        session.add(
            AnalysisRun(
                run_id="run_threaded",
                status="queued",
                ticker="NVDA",
                trade_date=date(2026, 1, 15),
                asset_type="stock",
                analysts=["market"],
                user_id="__system__",
                created_at=now,
            )
        )
        session.commit()

    result = {}

    def load_run() -> None:
        with Session() as session:
            saved = session.get(AnalysisRun, "run_threaded")
            result["ticker"] = saved.ticker if saved else None

    thread = Thread(target=load_run)
    thread.start()
    thread.join()

    assert result["ticker"] == "NVDA"


def test_ensure_additive_schema_reverts_minimax_cn_anthropic_url_to_v1():
    """The startup migration heals rows that were previously written to the
    Anthropic-compatible endpoint, putting them back on the OpenAI-compatible
    /v1 path which is what our LLM client expects. Custom proxy URLs that
    users have explicitly set must not be touched."""
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    now = datetime.now(timezone.utc)

    with Session() as session:
        session.add_all(
            [
                User(
                    user_id="usr_minimax",
                    username="minimax_user",
                    password_hash="hash",
                    role="operator",
                    is_active=True,
                    created_at=now,
                ),
                User(
                    user_id="usr_custom",
                    username="custom_user",
                    password_hash="hash",
                    role="operator",
                    is_active=True,
                    created_at=now,
                ),
            ]
        )
        session.add(
            UserModelSetting(
                user_id="usr_minimax",
                llm_provider="minimax-cn",
                deep_think_llm="MiniMax-M2.7",
                quick_think_llm="MiniMax-M2.7-highspeed",
                backend_url="https://api.minimaxi.com/anthropic",
                encrypted_api_key=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            UserModelSetting(
                user_id="usr_custom",
                llm_provider="minimax-cn",
                deep_think_llm="MiniMax-M2.7",
                quick_think_llm="MiniMax-M2.7-highspeed",
                backend_url="https://gateway.example.com/minimax",
                encrypted_api_key=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    ensure_additive_schema(engine)

    with Session() as session:
        assert (
            session.get(UserModelSetting, "usr_minimax").backend_url
            == "https://api.minimaxi.com/v1"
        )
        assert (
            session.get(UserModelSetting, "usr_custom").backend_url
            == "https://gateway.example.com/minimax"
        )


def test_repository_creates_run_and_queued_event():
    session = _session()
    repo = AnalysisRunRepository(session)

    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    session.commit()

    assert run.run_id.startswith("run_")
    assert run.status == "queued"
    events = repo.list_events(run.run_id)
    assert [event.event_type for event in events] == ["run_queued"]


def test_analysis_run_capacity_columns_exist():
    session = _session()
    repo = AnalysisRunRepository(session)

    run = repo.create_run(
        "NVDA",
        date(2026, 1, 15),
        "stock",
        ["market"],
        user_id="usr_1",
        llm_config={"llm_provider": "openai"},
    )
    assert run.updated_at is not None

    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.priority == 0
    assert saved.attempt_count == 0
    assert saved.max_attempts == 2
    assert saved.current_phase is None
    assert saved.progress_percent is None
    assert saved.dispatched_at is None
    assert saved.heartbeat_at is None
    assert saved.lease_expires_at is None
    assert saved.updated_at is not None


def test_artifact_and_memory_models_persist():
    session = _session()
    now = datetime.now(timezone.utc)
    run = AnalysisRun(
        run_id="run_schema",
        status="queued",
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        user_id="usr_1",
        llm_config={},
        current_step=None,
        celery_task_id=None,
        error=None,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.add(
        AnalysisRunArtifact(
            artifact_id="art_1",
            run_id="run_schema",
            kind="report_md",
            storage_backend="local",
            storage_key="artifacts/run_schema/reports/complete_report.md",
            content_type="text/markdown",
            size_bytes=12,
            sha256="abc",
            created_at=now,
        )
    )
    session.add(
        AnalysisMemoryEntry(
            user_id="usr_1",
            run_id="run_schema",
            ticker="NVDA",
            trade_date=date(2026, 1, 15),
            rating="Hold",
            decision_markdown="Rating: Hold",
            pending=True,
            created_at=now,
        )
    )
    session.commit()

    assert session.get(AnalysisRunArtifact, "art_1").run_id == "run_schema"
    assert session.query(AnalysisMemoryEntry).one().ticker == "NVDA"


def test_repository_stores_success_result():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.mark_running(run.run_id)
    repo.store_success(
        run_id=run.run_id,
        decision="Hold",
        reports={"final_trade_decision": "Rating: Hold"},
        final_state={"company_of_interest": "NVDA"},
    )
    session.commit()

    saved = repo.get_run(run.run_id)
    result = repo.get_result(run.run_id)
    assert saved.status == "succeeded"
    assert saved.current_step == "Completed"
    assert result.decision == "Hold"
    assert repo.list_events(run.run_id)[-1].event_type == "run_succeeded"


def test_repository_stores_failure():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.mark_running(run.run_id)
    repo.store_failure(run.run_id, "provider failed")
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert saved.error == "provider failed"
    assert repo.list_events(run.run_id)[-1].event_type == "run_failed"


def test_repository_cancels_queued_run():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )

    cancelled = repo.cancel_run(run.run_id, "user requested cancellation")
    session.commit()

    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    assert cancelled.current_step == "Cancelled"
    assert cancelled.error == "user requested cancellation"
    assert repo.list_events(run.run_id)[-1].event_type == "run_cancelled"


def test_repository_cancels_running_run():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.mark_running(run.run_id)

    repo.cancel_run(run.run_id, "user requested cancellation")
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "cancelling"
    assert saved.current_step == "Cancelling"
    assert [event.event_type for event in repo.list_events(run.run_id)] == [
        "run_queued",
        "run_started",
        "run_cancelling",
    ]


def test_repository_cancels_dispatching_run_immediately():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    run.status = "dispatching"
    run.celery_task_id = "task-dispatched"
    run.dispatched_at = utcnow()

    repo.cancel_run(run.run_id, "user requested cancellation")
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "cancelled"
    assert saved.finished_at is not None
    assert saved.current_step == "Cancelled"
    assert [event.event_type for event in repo.list_events(run.run_id)] == [
        "run_queued",
        "run_cancelled",
    ]


def test_cancelled_run_cannot_be_marked_successful_or_failed_or_running():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.cancel_run(run.run_id, "user requested cancellation")

    with pytest.raises(ValueError, match="cancelled"):
        repo.mark_running(run.run_id)
    with pytest.raises(ValueError, match="cancelled"):
        repo.store_success(run.run_id, "Hold", {}, {})
    with pytest.raises(ValueError, match="cancelled"):
        repo.store_failure(run.run_id, "provider failed")


def test_store_success_returns_persistent_result():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    returned = repo.store_success(
        run_id=run.run_id,
        decision="Hold",
        reports={"final_trade_decision": "Rating: Hold"},
        final_state={"company_of_interest": "NVDA"},
    )
    session.commit()

    assert returned is repo.get_result(run.run_id)


def test_success_cannot_be_overwritten_by_failure():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.store_success(
        run_id=run.run_id,
        decision="Hold",
        reports={"final_trade_decision": "Rating: Hold"},
        final_state={"company_of_interest": "NVDA"},
    )

    with pytest.raises(ValueError):
        repo.store_failure(run.run_id, "provider failed")
    session.commit()

    saved = repo.get_run(run.run_id)
    result = repo.get_result(run.run_id)
    assert saved.status == "succeeded"
    assert result.decision == "Hold"


def test_failure_cannot_be_overwritten_by_success():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.store_failure(run.run_id, "provider failed")

    with pytest.raises(ValueError):
        repo.store_success(
            run_id=run.run_id,
            decision="Hold",
            reports={"final_trade_decision": "Rating: Hold"},
            final_state={"company_of_interest": "NVDA"},
        )
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "failed"
    assert repo.get_result(run.run_id) is None


def test_mark_running_is_idempotent_for_running_status():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
    )
    repo.mark_running(run.run_id)
    session.commit()
    first_started_at = repo.get_run(run.run_id).started_at

    repo.mark_running(run.run_id)
    session.commit()

    saved = repo.get_run(run.run_id)
    event_types = [event.event_type for event in repo.list_events(run.run_id)]
    assert saved.started_at == first_started_at
    assert event_types == ["run_queued", "run_started"]


def test_scoped_repository_cannot_claim_other_users_run_for_dispatch():
    session = _session()
    unscoped_repo = AnalysisRunRepository(session)
    run = unscoped_repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        user_id="usr_b",
    )
    session.commit()

    scoped_repo = AnalysisRunRepository(session, user_id="usr_a")
    claimed = scoped_repo.claim_next_queued_for_dispatch(
        user_id="usr_b",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
    )
    session.commit()

    saved = unscoped_repo.get_run(run.run_id)
    assert claimed is None
    assert saved.status == "queued"
    assert saved.dispatched_at is None
    assert saved.lease_expires_at is None
    assert [event.event_type for event in unscoped_repo.list_events(run.run_id)] == [
        "run_queued"
    ]


def test_scoped_repository_cannot_claim_other_users_run_as_running():
    session = _session()
    unscoped_repo = AnalysisRunRepository(session)
    run = unscoped_repo.create_run(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        asset_type="stock",
        analysts=["market"],
        user_id="usr_b",
    )
    session.commit()

    scoped_repo = AnalysisRunRepository(session, user_id="usr_a")
    claimed = scoped_repo.claim_queued_run(run.run_id)
    session.commit()

    saved = unscoped_repo.get_run(run.run_id)
    assert claimed is None
    assert saved.status == "queued"
    assert saved.started_at is None
    assert [event.event_type for event in unscoped_repo.list_events(run.run_id)] == [
        "run_queued"
    ]
