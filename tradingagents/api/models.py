from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from tradingagents.api.db import Base


JsonType = JSON().with_variant(JSONB, "postgresql")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    analysts: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    current_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_analysis_runs_created_at", "created_at"),
        Index("idx_analysis_runs_ticker_trade_date", "ticker", "trade_date"),
    )


class AnalysisRunEvent(Base):
    __tablename__ = "analysis_run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_analysis_run_events_run_id_id", "run_id", "id"),
        Index("idx_analysis_run_events_created_at", "created_at"),
    )


class AnalysisRunResult(Base):
    __tablename__ = "analysis_run_results"

    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reports: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    final_state: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
