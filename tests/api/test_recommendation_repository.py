from datetime import date, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from tradingagents.api import recommendation_repository as recommendation_repository_module
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.models import (
    AnalysisRun,
    AnalysisRunResult,
    RecommendationItem,
    User,
)
from tradingagents.api.recommendation_repository import RecommendationRepository
from tradingagents.api.repositories import utcnow


def _session():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


@pytest.fixture
def user():
    return User(
        user_id="usr_1",
        username="alice",
        password_hash="hash",
        role="operator",
        is_active=True,
        language="zh",
        created_at=utcnow(),
    )


def _add_user(session, user_id="usr_1", username="alice") -> User:
    user = User(
        user_id=user_id,
        username=username,
        password_hash="hash",
        role="operator",
        is_active=True,
        language="zh",
        created_at=utcnow(),
    )
    session.add(user)
    session.flush()
    return user


def _recommendation_item(ticker: str, priority: int = 1) -> dict[str, object]:
    return {
        "ticker": ticker,
        "source": "watchlist",
        "priority": priority,
        "reason": f"{ticker} reason",
        "risk": f"{ticker} risk",
    }


def _add_run_result(
    session,
    *,
    run_id: str,
    user_id: str,
    ticker: str,
    trade_date: date,
    status: str = "succeeded",
    reports: dict[str, object] | None = None,
    final_state: dict[str, object] | None = None,
    created_offset_days: int = 0,
    finished_offset_days: int | None = 0,
) -> None:
    now = utcnow()
    created_at = now + timedelta(days=created_offset_days)
    finished_at = (
        now + timedelta(days=finished_offset_days)
        if finished_offset_days is not None
        else None
    )
    session.add(
        AnalysisRun(
            run_id=run_id,
            status=status,
            ticker=ticker,
            trade_date=trade_date,
            asset_type="stock",
            analysts=["market"],
            user_id=user_id,
            created_at=created_at,
            updated_at=created_at,
            finished_at=finished_at,
        )
    )
    session.add(
        AnalysisRunResult(
            run_id=run_id,
            decision="Hold",
            reports=reports or {},
            final_state=final_state or {},
            created_at=created_at,
        )
    )


def test_watchlist_upsert_normalizes_deduplicates_and_persists(user):
    with _session() as session:
        session.add(user)
        session.commit()
        repo = RecommendationRepository(session)

        row = repo.upsert_watchlist(user.user_id, [" nvda ", "AAPL", "nvda", "msft"])
        session.commit()

        assert row.tickers == ["NVDA", "AAPL", "MSFT"]
        assert repo.get_watchlist(user.user_id).tickers == ["NVDA", "AAPL", "MSFT"]


def test_watchlist_rejects_empty_list(user):
    with _session() as session:
        session.add(user)
        session.commit()
        repo = RecommendationRepository(session)

        with pytest.raises(ValueError, match="at least one ticker"):
            repo.upsert_watchlist(user.user_id, [])


def test_watchlist_rejects_invalid_ticker(user):
    with _session() as session:
        session.add(user)
        session.commit()
        repo = RecommendationRepository(session)

        with pytest.raises(ValueError, match="invalid ticker"):
            repo.upsert_watchlist(user.user_id, ["AAPL", "../BAD"])


def test_create_batch_persists_succeeded_batch_and_normalized_recommended_items():
    with _session() as session:
        user = _add_user(session)
        repo = RecommendationRepository(session)

        batch = repo.create_batch(
            user.user_id,
            ["NVDA", "AAPL"],
            {"llm_provider": "openai", "quick_think_llm": "gpt-5-mini"},
            [
                _recommendation_item(" msft ", priority=2),
                _recommendation_item("aapl", priority=1),
            ],
        )
        session.commit()

        saved = repo.get_batch(user.user_id, batch.batch_id)
        assert saved is not None
        assert saved.batch_id.startswith("rec_")
        assert saved.status == "succeeded"
        assert saved.watchlist_snapshot == ["NVDA", "AAPL"]
        assert saved.model_snapshot == {
            "llm_provider": "openai",
            "quick_think_llm": "gpt-5-mini",
        }
        assert saved.prompt_version == "stock-recommendations-v1"
        assert saved.error is None

        items = repo.list_items(user.user_id, batch.batch_id)
        assert [item.ticker for item in items] == ["AAPL", "MSFT"]
        assert [item.priority for item in items] == [1, 2]
        assert all(item.item_id.startswith("reci_") for item in items)
        assert all(item.batch_id == batch.batch_id for item in items)
        assert all(item.user_id == user.user_id for item in items)
        assert all(item.status == "recommended" for item in items)
        assert all(item.run_id is None for item in items)
        assert all(item.error is None for item in items)


def test_create_batch_rejects_invalid_item_ticker():
    with _session() as session:
        user = _add_user(session)
        repo = RecommendationRepository(session)

        with pytest.raises(ValueError, match="invalid ticker"):
            repo.create_batch(
                user.user_id,
                ["NVDA"],
                {"llm_provider": "openai"},
                [_recommendation_item("../BAD")],
            )


def test_create_batch_invalid_later_item_does_not_persist_partial_rows():
    with _session() as session:
        user = _add_user(session)
        repo = RecommendationRepository(session)

        with pytest.raises(ValueError, match="invalid ticker"):
            repo.create_batch(
                user.user_id,
                ["NVDA"],
                {"llm_provider": "openai"},
                [
                    _recommendation_item("NVDA"),
                    _recommendation_item("../BAD"),
                ],
            )
        session.commit()

        assert repo.list_batches(user.user_id) == []
        assert session.query(RecommendationItem).count() == 0


def test_list_items_orders_by_priority_then_created_at():
    with _session() as session:
        user = _add_user(session)
        repo = RecommendationRepository(session)

        batch = repo.create_batch(
            user.user_id,
            ["NVDA", "AAPL", "MSFT"],
            {"llm_provider": "openai"},
            [
                _recommendation_item("MSFT", priority=2),
                _recommendation_item("AAPL", priority=1),
                _recommendation_item("NVDA", priority=1),
            ],
        )
        session.flush()
        base = utcnow()
        for item in repo.list_items(user.user_id, batch.batch_id):
            if item.ticker == "NVDA":
                item.created_at = base
            elif item.ticker == "AAPL":
                item.created_at = base + timedelta(seconds=1)
            else:
                item.created_at = base - timedelta(seconds=1)
        session.commit()

        assert [item.ticker for item in repo.list_items(user.user_id, batch.batch_id)] == [
            "NVDA",
            "AAPL",
            "MSFT",
        ]


def test_list_items_uses_item_id_as_stable_final_order(monkeypatch):
    item_ids = iter(["reci_c", "reci_a", "reci_b"])
    monkeypatch.setattr(
        recommendation_repository_module,
        "_new_item_id",
        lambda: next(item_ids),
    )

    with _session() as session:
        user = _add_user(session)
        repo = RecommendationRepository(session)

        batch = repo.create_batch(
            user.user_id,
            ["NVDA", "AAPL", "MSFT"],
            {"llm_provider": "openai"},
            [
                _recommendation_item("NVDA", priority=1),
                _recommendation_item("AAPL", priority=1),
                _recommendation_item("MSFT", priority=1),
            ],
        )
        session.commit()

        assert [item.item_id for item in repo.list_items(user.user_id, batch.batch_id)] == [
            "reci_a",
            "reci_b",
            "reci_c",
        ]


def test_get_batch_and_list_batches_are_user_scoped():
    with _session() as session:
        first_user = _add_user(session, "usr_1", "alice")
        second_user = _add_user(session, "usr_2", "bob")
        repo = RecommendationRepository(session)

        older = repo.create_batch(
            first_user.user_id,
            ["NVDA"],
            {"llm_provider": "openai"},
            [_recommendation_item("NVDA")],
        )
        newer = repo.create_batch(
            first_user.user_id,
            ["AAPL"],
            {"llm_provider": "openai"},
            [_recommendation_item("AAPL")],
        )
        other_user = repo.create_batch(
            second_user.user_id,
            ["MSFT"],
            {"llm_provider": "openai"},
            [_recommendation_item("MSFT")],
        )
        older.created_at = utcnow() - timedelta(days=2)
        newer.created_at = utcnow() - timedelta(days=1)
        other_user.created_at = utcnow()
        session.commit()

        assert repo.get_batch(first_user.user_id, older.batch_id) == older
        assert repo.get_batch(first_user.user_id, other_user.batch_id) is None
        assert [batch.batch_id for batch in repo.list_batches(first_user.user_id)] == [
            newer.batch_id,
            older.batch_id,
        ]
        assert [batch.batch_id for batch in repo.list_batches(second_user.user_id)] == [
            other_user.batch_id
        ]


def test_recent_analysis_context_returns_scoped_truncated_final_decisions():
    with _session() as session:
        user = _add_user(session, "usr_1", "alice")
        other = _add_user(session, "usr_2", "bob")
        reports_decision = "R" * 700
        final_state_decision = "F" * 650
        _add_run_result(
            session,
            run_id="run_reports",
            user_id=user.user_id,
            ticker="NVDA",
            trade_date=date(2026, 1, 15),
            reports={"final_trade_decision": reports_decision},
            final_state={"final_trade_decision": "unused fallback"},
            created_offset_days=2,
            finished_offset_days=2,
        )
        _add_run_result(
            session,
            run_id="run_final_state",
            user_id=user.user_id,
            ticker="AAPL",
            trade_date=date(2026, 1, 14),
            reports={},
            final_state={"final_trade_decision": final_state_decision},
            created_offset_days=1,
            finished_offset_days=1,
        )
        _add_run_result(
            session,
            run_id="run_other_user",
            user_id=other.user_id,
            ticker="MSFT",
            trade_date=date(2026, 1, 13),
            reports={"final_trade_decision": "other user"},
            created_offset_days=3,
            finished_offset_days=3,
        )
        _add_run_result(
            session,
            run_id="run_failed",
            user_id=user.user_id,
            ticker="TSLA",
            trade_date=date(2026, 1, 12),
            status="failed",
            reports={"final_trade_decision": "failed"},
            created_offset_days=4,
            finished_offset_days=4,
        )
        session.commit()

        context = RecommendationRepository(session).recent_analysis_context(
            user.user_id, limit=2
        )

        assert context == [
            {
                "ticker": "NVDA",
                "trade_date": "2026-01-15",
                "decision": "Hold",
                "final_trade_decision": reports_decision[:600],
            },
            {
                "ticker": "AAPL",
                "trade_date": "2026-01-14",
                "decision": "Hold",
                "final_trade_decision": final_state_decision[:600],
            },
        ]
