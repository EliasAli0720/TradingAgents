from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from tradingagents.api.db import Base


JsonType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    analysts: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    llm_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default=text("2")
    )
    current_phase: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    progress_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_analysis_runs_created_at", "created_at"),
        Index("idx_analysis_runs_ticker_trade_date", "ticker", "trade_date"),
        Index("idx_analysis_runs_user_id_created_at", "user_id", "created_at"),
    )


class AnalysisRunArtifact(Base):
    __tablename__ = "analysis_run_artifacts"

    artifact_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("analysis_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String, nullable=False)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_analysis_run_artifacts_run_id_kind", "run_id", "kind"),)


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


class AnalysisRunTranslation(Base):
    """Per-section report translations, written incrementally.

    Decoupled from analysis_run_results so sections can be translated while
    the pipeline is still running (the result row only exists once the run
    succeeds). English originals live in AnalysisRunResult.reports and are
    never duplicated here. Composite PK keeps each (run, language, section)
    translated at most once.
    """

    __tablename__ = "analysis_run_translations"

    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("analysis_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    lang: Mapped[str] = mapped_column(String, primary_key=True)
    section: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalysisMemoryEntry(Base):
    __tablename__ = "analysis_memory_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("analysis_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    rating: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    decision_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alpha_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    holding_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reflection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "idx_analysis_memory_entries_user_ticker_pending_created",
            "user_id",
            "ticker",
            "pending",
            "created_at",
        ),
    )


class UserWatchlist(Base):
    __tablename__ = "user_watchlists"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    tickers: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecommendationBatch(Base):
    __tablename__ = "recommendation_batches"

    batch_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    watchlist_snapshot: Mapped[list[str]] = mapped_column(JsonType, nullable=False)
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_recommendation_batches_user_created", "user_id", "created_at"),
    )


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("recommendation_batches.batch_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("analysis_runs.run_id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_recommendation_items_user_status", "user_id", "status"),
        Index("idx_recommendation_items_batch_priority", "batch_id", "priority"),
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    language: Mapped[str] = mapped_column(String, nullable=False, default="zh")
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


class UserModelSetting(Base):
    __tablename__ = "user_model_settings"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    deep_think_llm: Mapped[str] = mapped_column(String, nullable=False)
    quick_think_llm: Mapped[str] = mapped_column(String, nullable=False)
    backend_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserTranslationSetting(Base):
    """Per-user model dedicated to report translation, separate from the
    analysis model. Only a single model (no deep/quick split)."""

    __tablename__ = "user_translation_settings"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    backend_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LLMProviderOption(Base):
    __tablename__ = "llm_provider_options"

    provider_id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    required_env_var: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    default_backend_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    backend_url_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_custom_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class LLMModelOption(Base):
    __tablename__ = "llm_model_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(
        String, ForeignKey("llm_provider_options.provider_id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String, nullable=False)
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("provider_id", "mode", "model_id", name="uq_llm_model_option"),
        Index("idx_llm_model_options_provider_mode_order", "provider_id", "mode", "sort_order"),
    )


# --------------------------------------------------------------------------- #
# Broker integration (IBKR TWS API, single platform account)                  #
#                                                                             #
# These mirror the platform broker state written by the IBKR connector and    #
# the trade approval / order lifecycle. See                                   #
# docs/superpowers/specs/2026-05-29-ibkr-tws-api-integration-design.md         #
# --------------------------------------------------------------------------- #


class BrokerStatus(Base):
    """Singleton row holding the platform broker connection health.

    Written by the connector; read by /broker/status. One row, id="platform".
    """

    __tablename__ = "broker_status"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    broker: Mapped[str] = mapped_column(String, nullable=False, default="ibkr")
    gateway_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    brokerage_session: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    account_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_refresh_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class TradeApproval(Base):
    """An agent-generated (or manual) trade proposal awaiting human approval.

    status: pending -> approved -> submitted | failed; pending -> rejected;
    pending -> expired.
    """

    __tablename__ = "trade_approvals"

    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    conid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    side: Mapped[str] = mapped_column(String, nullable=False)
    order_type: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_in_force: Mapped[str] = mapped_column(String, nullable=False, default="day")
    estimated_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    whatif_init_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    whatif_commission: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_verdict: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", index=True
    )
    approved_by_user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_order_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        Index(
            "idx_trade_approvals_user_status_created",
            "requested_by_user_id",
            "status",
            "created_at",
        ),
    )


class BrokerOrder(Base):
    """Mirror of an order placed at IBKR, kept in sync by the connector."""

    __tablename__ = "broker_orders"

    broker_order_id: Mapped[str] = mapped_column(String, primary_key=True)
    approval_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("trade_approvals.approval_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    requested_by_user_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    account_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    conid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    side: Mapped[str] = mapped_column(String, nullable=False)
    order_type: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_in_force: Mapped[str] = mapped_column(String, nullable=False, default="day")
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    filled_qty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    filled_avg_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    raw_event: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)

    __table_args__ = (Index("idx_broker_orders_updated_at", "updated_at"),)


class PortfolioSnapshot(Base):
    """Daily account-equity snapshot, scoped per (user, account, broker).

    Powers the equity curve / Sharpe / drawdown / total-return analytics. The
    desktop pushes the live account equity while connected; exactly one row per
    (user, account, broker, date), continuously updated to the day's latest
    value. The (user, account, broker) tuple is the segmentation unit so future
    additional accounts (other TWS accounts or other brokers) stay isolated.
    """

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False)
    broker: Mapped[str] = mapped_column(
        String, nullable=False, default="ibkr", server_default=text("'ibkr'")
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    invested_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    open_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "account_id", "broker", "snapshot_date", name="uq_portfolio_snapshot_day"
        ),
        Index(
            "idx_portfolio_snapshots_user_account_date",
            "user_id",
            "account_id",
            "snapshot_date",
        ),
    )


class BrokerCredential(Base):
    """Per-user broker OAuth credentials (Webull Connect API, multi-tenant).

    Unlike IBKR (one shared platform account on a local socket), Webull is a
    cloud broker where each user authorises their *own* account. The server
    keeps that user's short-lived access token + refresh token here, encrypted
    at rest with the same Fernet key as model API keys (see ``crypto.py``).
    Tokens are never returned to the client or logged. One row per (user, broker).

    See docs/superpowers/specs/2026-05-31-webull-server-broker-design.md §4
    """

    __tablename__ = "broker_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    broker: Mapped[str] = mapped_column(
        String, nullable=False, default="webull", server_default=text("'webull'")
    )
    account_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    region: Mapped[str] = mapped_column(
        String, nullable=False, default="us", server_default=text("'us'")
    )
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refresh_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scope: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # connected | expired | revoked
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="connected", server_default=text("'connected'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "broker", name="uq_broker_credential_user_broker"),
    )
