from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.api.models import (
    AnalysisRun,
    AnalysisRunResult,
    RecommendationBatch,
    RecommendationItem,
    UserWatchlist,
)
from tradingagents.api.repositories import utcnow


_TICKER_RE = re.compile(r"^[A-Z0-9._\-^]{1,32}$")


def _new_batch_id() -> str:
    return f"rec_{uuid4().hex}"


def _new_item_id() -> str:
    return f"reci_{uuid4().hex}"


def normalize_tickers(tickers: list[str], max_count: int = 50) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = raw.strip().upper()
        if not ticker:
            continue
        if not _TICKER_RE.fullmatch(ticker):
            raise ValueError(f"invalid ticker: {raw}")
        if ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(ticker)

    if not normalized:
        raise ValueError("at least one ticker is required")
    if len(normalized) > max_count:
        raise ValueError(f"watchlist cannot exceed {max_count} tickers")
    return normalized


class RecommendationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_watchlist(self, user_id: str) -> UserWatchlist | None:
        return self.session.get(UserWatchlist, user_id)

    def upsert_watchlist(self, user_id: str, tickers: list[str]) -> UserWatchlist:
        normalized = normalize_tickers(tickers)
        now = utcnow()
        row = self.get_watchlist(user_id)
        if row is None:
            row = UserWatchlist(
                user_id=user_id,
                tickers=normalized,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
            return row

        row.tickers = normalized
        row.updated_at = now
        return row

    def create_batch(
        self,
        user_id: str,
        watchlist_snapshot: list[str],
        model_snapshot: dict[str, Any],
        items: list[dict[str, Any]],
        *,
        prompt_version: str = "stock-recommendations-v1",
    ) -> RecommendationBatch:
        normalized_items: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            normalized_items.append(
                {
                    "ticker": normalize_tickers([item["ticker"]])[0],
                    "source": item["source"],
                    "priority": int(item.get("priority") or index),
                    "reason": item["reason"],
                    "risk": item["risk"],
                }
            )

        now = utcnow()
        batch = RecommendationBatch(
            batch_id=_new_batch_id(),
            user_id=user_id,
            status="succeeded",
            watchlist_snapshot=list(watchlist_snapshot),
            model_snapshot=dict(model_snapshot),
            prompt_version=prompt_version,
            error=None,
            created_at=now,
        )
        self.session.add(batch)

        for item in normalized_items:
            self.session.add(
                RecommendationItem(
                    item_id=_new_item_id(),
                    batch_id=batch.batch_id,
                    user_id=user_id,
                    ticker=item["ticker"],
                    source=item["source"],
                    priority=item["priority"],
                    reason=item["reason"],
                    risk=item["risk"],
                    status="recommended",
                    run_id=None,
                    error=None,
                    created_at=now,
                    updated_at=now,
                )
            )

        return batch

    def get_batch(self, user_id: str, batch_id: str) -> RecommendationBatch | None:
        stmt = select(RecommendationBatch).where(
            RecommendationBatch.user_id == user_id,
            RecommendationBatch.batch_id == batch_id,
        )
        return self.session.scalar(stmt)

    def list_batches(self, user_id: str, limit: int = 20) -> list[RecommendationBatch]:
        stmt = (
            select(RecommendationBatch)
            .where(RecommendationBatch.user_id == user_id)
            .order_by(RecommendationBatch.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_items(self, user_id: str, batch_id: str) -> list[RecommendationItem]:
        stmt = (
            select(RecommendationItem)
            .where(
                RecommendationItem.user_id == user_id,
                RecommendationItem.batch_id == batch_id,
            )
            .order_by(
                RecommendationItem.priority.asc(),
                RecommendationItem.created_at.asc(),
                RecommendationItem.item_id.asc(),
            )
        )
        return list(self.session.scalars(stmt))

    def recent_analysis_context(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        stmt = (
            select(AnalysisRun, AnalysisRunResult)
            .join(AnalysisRunResult, AnalysisRunResult.run_id == AnalysisRun.run_id)
            .where(AnalysisRun.user_id == user_id, AnalysisRun.status == "succeeded")
            .order_by(
                AnalysisRun.finished_at.desc().nullslast(),
                AnalysisRun.created_at.desc(),
            )
            .limit(limit)
        )

        rows = self.session.execute(stmt).all()
        return [
            {
                "ticker": run.ticker,
                "trade_date": run.trade_date.isoformat(),
                "decision": result.decision,
                "final_trade_decision": self._final_trade_decision(result),
            }
            for run, result in rows
        ]

    def _final_trade_decision(self, result: AnalysisRunResult) -> str:
        if "final_trade_decision" in result.reports:
            return str(result.reports["final_trade_decision"])[:600]
        return str(result.final_state.get("final_trade_decision", ""))[:600]
