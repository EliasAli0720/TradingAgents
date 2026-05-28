from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.api.models import AnalysisMemoryEntry
from tradingagents.api.repositories import utcnow


class AnalysisMemoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def store_decision(
        self,
        user_id: str,
        run_id: str,
        ticker: str,
        trade_date: date,
        decision_markdown: str,
        *,
        pending: bool = True,
        reflection: str | None = None,
    ) -> AnalysisMemoryEntry:
        entry = AnalysisMemoryEntry(
            user_id=user_id,
            run_id=run_id,
            ticker=ticker.upper(),
            trade_date=trade_date,
            rating=parse_rating(decision_markdown),
            decision_markdown=decision_markdown,
            pending=pending,
            reflection=reflection,
            created_at=utcnow(),
        )
        self.session.add(entry)
        return entry

    def get_past_context(
        self,
        user_id: str,
        ticker: str,
        n_same: int = 5,
        n_cross: int = 3,
    ) -> str:
        ticker = ticker.upper()
        stmt = (
            select(AnalysisMemoryEntry)
            .where(
                AnalysisMemoryEntry.user_id == user_id,
                AnalysisMemoryEntry.pending.is_(False),
            )
            .order_by(
                AnalysisMemoryEntry.trade_date.desc(),
                AnalysisMemoryEntry.created_at.desc(),
                AnalysisMemoryEntry.id.desc(),
            )
        )
        same: list[AnalysisMemoryEntry] = []
        cross: list[AnalysisMemoryEntry] = []
        for entry in self.session.scalars(stmt):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if entry.ticker == ticker and len(same) < n_same:
                same.append(entry)
            elif entry.ticker != ticker and len(cross) < n_cross:
                cross.append(entry)

        if not same and not cross:
            return ""

        parts: list[str] = []
        if same:
            parts.append(f"Past analyses of {ticker} (most recent first):")
            parts.extend(_format_full(entry) for entry in same)
        if cross:
            parts.append("Recent cross-ticker lessons:")
            parts.extend(_format_reflection_only(entry) for entry in cross)
        return "\n\n".join(parts)

    def lock_pending_for_ticker(
        self,
        user_id: str,
        ticker: str,
    ) -> list[AnalysisMemoryEntry]:
        stmt = (
            select(AnalysisMemoryEntry)
            .where(
                AnalysisMemoryEntry.user_id == user_id,
                AnalysisMemoryEntry.ticker == ticker.upper(),
                AnalysisMemoryEntry.pending.is_(True),
            )
            .order_by(AnalysisMemoryEntry.trade_date.asc(), AnalysisMemoryEntry.id.asc())
            .with_for_update()
        )
        return list(self.session.scalars(stmt))

    def resolve_pending(
        self,
        entry_id: int,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
    ) -> AnalysisMemoryEntry | None:
        entry = self.session.get(AnalysisMemoryEntry, entry_id)
        if entry is None or not entry.pending:
            return entry
        entry.pending = False
        entry.raw_return = raw_return
        entry.alpha_return = alpha_return
        entry.holding_days = holding_days
        entry.reflection = reflection
        return entry


def _format_full(entry: AnalysisMemoryEntry) -> str:
    tag = _entry_tag(entry)
    reflection = f"\nREFLECTION:\n{entry.reflection}" if entry.reflection else ""
    return f"{tag}\nDECISION:\n{entry.decision_markdown}{reflection}"


def _format_reflection_only(entry: AnalysisMemoryEntry) -> str:
    tag = _entry_tag(entry)
    if entry.reflection:
        return f"{tag}\n{entry.reflection}"
    return f"{tag}\n{entry.decision_markdown}"


def _entry_tag(entry: AnalysisMemoryEntry) -> str:
    fields = [
        entry.trade_date.isoformat(),
        entry.ticker,
        entry.rating or "Unknown",
    ]
    if entry.raw_return is not None and entry.alpha_return is not None:
        fields.extend([f"{entry.raw_return:+.1%}", f"{entry.alpha_return:+.1%}"])
    if entry.holding_days is not None:
        fields.append(f"{entry.holding_days}d")
    elif entry.pending:
        fields.append("pending")
    return "[" + " | ".join(fields) + "]"
