"""Per-(user, account, broker) portfolio persistence + analytics source.

Everything here is strictly scoped to ONE (user_id, account_id, broker) tuple —
the segmentation unit so future additional accounts stay isolated. Trade history
and realised P&L are derived from the existing ``broker_orders`` mirror (filled
orders placed via this app); the equity curve / Sharpe / drawdown come from
``portfolio_snapshots`` the desktop pushes while connected.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from tradingagents.api.models import BrokerOrder, PortfolioSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PortfolioRepository:
    def __init__(self, session: Session, user_id: str, account_id: str, broker: str = "ibkr"):
        self.session = session
        self.user_id = user_id
        self.account_id = account_id
        self.broker = broker

    # -- filled orders: source for trade history + realised P&L ----------- #

    def filled_orders(self, limit: int = 5000) -> list[BrokerOrder]:
        stmt = (
            select(BrokerOrder)
            .where(
                BrokerOrder.requested_by_user_id == self.user_id,
                BrokerOrder.account_id == self.account_id,
                BrokerOrder.filled_qty > 0,
            )
            .order_by(asc(BrokerOrder.submitted_at), asc(BrokerOrder.updated_at))
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    # -- snapshots -------------------------------------------------------- #

    def list_snapshots(self, limit: int = 365) -> list[PortfolioSnapshot]:
        stmt = (
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.user_id == self.user_id,
                PortfolioSnapshot.account_id == self.account_id,
                PortfolioSnapshot.broker == self.broker,
            )
            .order_by(asc(PortfolioSnapshot.snapshot_date))
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def _latest_before(self, day: date) -> Optional[PortfolioSnapshot]:
        stmt = (
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.user_id == self.user_id,
                PortfolioSnapshot.account_id == self.account_id,
                PortfolioSnapshot.broker == self.broker,
                PortfolioSnapshot.snapshot_date < day,
            )
            .order_by(desc(PortfolioSnapshot.snapshot_date))
            .limit(1)
        )
        return self.session.scalar(stmt)

    def upsert_snapshot(
        self,
        *,
        cash: float,
        invested_value: float,
        total_value: float,
        open_positions: int,
        day: Optional[date] = None,
    ) -> PortfolioSnapshot:
        day = day or _utcnow().date()
        existing = self.session.scalar(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.user_id == self.user_id,
                PortfolioSnapshot.account_id == self.account_id,
                PortfolioSnapshot.broker == self.broker,
                PortfolioSnapshot.snapshot_date == day,
            )
        )
        prev = self._latest_before(day)
        prev_value = prev.total_value if prev else total_value
        daily_pnl = total_value - prev_value
        daily_pnl_pct = (daily_pnl / prev_value) if prev_value else 0.0

        if existing is None:
            row = PortfolioSnapshot(
                user_id=self.user_id,
                account_id=self.account_id,
                broker=self.broker,
                snapshot_date=day,
                cash=cash,
                invested_value=invested_value,
                total_value=total_value,
                daily_pnl=daily_pnl,
                daily_pnl_pct=daily_pnl_pct,
                open_positions=open_positions,
                updated_at=_utcnow(),
            )
            self.session.add(row)
            return row

        existing.cash = cash
        existing.invested_value = invested_value
        existing.total_value = total_value
        existing.daily_pnl = daily_pnl
        existing.daily_pnl_pct = daily_pnl_pct
        existing.open_positions = open_positions
        existing.updated_at = _utcnow()
        return existing
