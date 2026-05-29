"""Unit tests for BrokerRepository: user scoping + approval state machine."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tradingagents.api.broker_repository import BrokerRepository, utcnow
from tradingagents.api.db import Base

pytestmark = pytest.mark.unit


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _mk(repo: BrokerRepository, user: str, ticker: str = "AAPL"):
    return repo.create_approval(
        requested_by_user_id=user,
        ticker=ticker,
        side="buy",
        order_type="market",
        quantity=10,
        estimated_price=300.0,
        estimated_value=3000.0,
    )


# --------------------------------------------------------------------------- #
# Scoping                                                                     #
# --------------------------------------------------------------------------- #


def test_user_cannot_read_another_users_approval():
    session = _session()
    admin = BrokerRepository(session)
    a = _mk(admin, "userA")
    session.commit()

    as_b = BrokerRepository(session, user_id="userB")
    assert as_b.get_approval(a.approval_id) is None

    as_a = BrokerRepository(session, user_id="userA")
    assert as_a.get_approval(a.approval_id).approval_id == a.approval_id

    # Admin (unscoped) sees it.
    assert BrokerRepository(session).get_approval(a.approval_id) is not None


def test_list_approvals_is_scoped_and_status_filtered():
    session = _session()
    admin = BrokerRepository(session)
    _mk(admin, "userA", "AAPL")
    _mk(admin, "userB", "NVDA")
    session.commit()

    assert len(BrokerRepository(session).list_approvals()) == 2
    assert len(BrokerRepository(session, user_id="userA").list_approvals()) == 1
    assert (
        len(BrokerRepository(session, user_id="userA").list_approvals(status="pending"))
        == 1
    )
    assert (
        len(BrokerRepository(session, user_id="userA").list_approvals(status="submitted"))
        == 0
    )


# --------------------------------------------------------------------------- #
# Approval state machine                                                      #
# --------------------------------------------------------------------------- #


def test_approve_then_submit_happy_path():
    session = _session()
    repo = BrokerRepository(session)
    a = _mk(repo, "u1")
    session.commit()

    repo.approve(a.approval_id, "admin1")
    assert a.status == "approved"
    assert a.approved_by_user_id == "admin1"
    assert a.approved_at is not None

    repo.mark_submitted(a.approval_id, "ORD123")
    assert a.status == "submitted"
    assert a.submitted_order_id == "ORD123"


def test_cannot_approve_twice():
    session = _session()
    repo = BrokerRepository(session)
    a = _mk(repo, "u1")
    repo.approve(a.approval_id, "admin1")
    with pytest.raises(ValueError):
        repo.approve(a.approval_id, "admin1")


def test_cannot_submit_before_approval():
    session = _session()
    repo = BrokerRepository(session)
    a = _mk(repo, "u1")
    with pytest.raises(ValueError):
        repo.mark_submitted(a.approval_id, "ORD1")


def test_reject_from_pending_then_cannot_approve():
    session = _session()
    repo = BrokerRepository(session)
    a = _mk(repo, "u1")
    repo.reject(a.approval_id, "admin1")
    assert a.status == "rejected"
    with pytest.raises(ValueError):
        repo.approve(a.approval_id, "admin1")


def test_mark_failed_from_approved():
    session = _session()
    repo = BrokerRepository(session)
    a = _mk(repo, "u1")
    repo.approve(a.approval_id, "admin1")
    repo.mark_failed(a.approval_id, "broker rejected")
    assert a.status == "failed"
    assert a.error == "broker rejected"


def test_expire_pending_older_than():
    session = _session()
    repo = BrokerRepository(session)
    a = _mk(repo, "u1")
    a.created_at = utcnow() - timedelta(days=2)
    session.commit()
    n = repo.expire_pending_older_than(utcnow() - timedelta(days=1))
    assert n == 1
    assert a.status == "expired"


# --------------------------------------------------------------------------- #
# Order mirror + status singleton                                             #
# --------------------------------------------------------------------------- #


def test_upsert_order_creates_then_updates():
    session = _session()
    repo = BrokerRepository(session)
    repo.upsert_order(
        broker_order_id="O1",
        ticker="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        status="pending",
        requested_by_user_id="u1",
    )
    session.commit()

    order = repo.upsert_order(
        broker_order_id="O1",
        ticker="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        status="filled",
        filled_qty=10,
        filled_avg_price=301.5,
    )
    session.commit()
    assert order.status == "filled"
    assert order.filled_avg_price == 301.5
    # still scoped: another user can't see it
    assert BrokerRepository(session, user_id="u2").get_order("O1") is None
    assert BrokerRepository(session, user_id="u1").get_order("O1") is not None


def test_status_singleton_upsert_and_get():
    session = _session()
    repo = BrokerRepository(session)
    assert repo.get_status() is None
    repo.upsert_status(gateway_online=True, account_id="DU1", paper=True)
    session.commit()
    s = repo.get_status()
    assert s.gateway_online is True
    assert s.account_id == "DU1"

    repo.upsert_status(gateway_online=False, last_error="socket dropped")
    session.commit()
    s2 = repo.get_status()
    assert s2.gateway_online is False
    assert s2.last_error == "socket dropped"
    assert s2.account_id == "DU1"  # unchanged field preserved
