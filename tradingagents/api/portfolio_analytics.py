"""Pure analytics over filled orders + equity snapshots (no DB, no broker).

Derives the trade ledger, closed round-trips (avg-cost matcher) with realised
P&L, and the performance metrics. Mirrors the math previously in
``tradingbot.portfolio.PortfolioManager`` but operates on the server's
``broker_orders`` mirror + ``portfolio_snapshots`` instead of local SQLite.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Optional


def _iso_date(dt) -> Optional[str]:
    return dt.date().isoformat() if dt is not None else None


def _days(d1: Optional[str], d2: Optional[str]) -> int:
    try:
        return (date.fromisoformat(d2) - date.fromisoformat(d1)).days
    except Exception:  # noqa: BLE001
        return 0


def trade_rows(orders) -> list[dict]:
    """Flatten filled orders into a trade ledger (newest first)."""
    rows = []
    for o in orders:
        price = o.filled_avg_price or 0.0
        rows.append(
            {
                "ticker": o.ticker,
                "side": o.side,
                "qty": o.filled_qty,
                "price": price,
                "total_value": o.filled_qty * price,
                "signal": o.status,
                "order_id": o.broker_order_id,
                "trade_date": _iso_date(o.submitted_at),
                "timestamp": o.submitted_at.isoformat() if o.submitted_at else None,
            }
        )
    rows.reverse()
    return rows


def closed_positions(orders) -> list[dict]:
    """Match buys/sells per ticker (avg-cost) into closed round-trips."""
    book: dict[str, dict] = defaultdict(lambda: {"qty": 0.0, "avg": 0.0, "open_date": None})
    closed: list[dict] = []
    for o in orders:
        qty = float(o.filled_qty or 0.0)
        price = float(o.filled_avg_price or 0.0)
        if qty <= 0:
            continue
        ticker = o.ticker.upper()
        b = book[ticker]
        when = _iso_date(o.submitted_at)
        if o.side.lower() == "buy":
            new_qty = b["qty"] + qty
            b["avg"] = (b["avg"] * b["qty"] + price * qty) / new_qty if new_qty > 0 else 0.0
            if b["qty"] <= 1e-9:
                b["open_date"] = when
            b["qty"] = new_qty
        else:  # sell closes against the average cost
            close_qty = min(qty, b["qty"])
            if close_qty > 0:
                realized = (price - b["avg"]) * close_qty
                pct = (price - b["avg"]) / b["avg"] if b["avg"] > 0 else 0.0
                closed.append(
                    {
                        "ticker": ticker,
                        "entry_price": b["avg"],
                        "exit_price": price,
                        "qty": close_qty,
                        "realized_pnl": realized,
                        "realized_pnl_pct": pct,
                        "entry_date": b["open_date"],
                        "exit_date": when,
                        "holding_days": _days(b["open_date"], when),
                    }
                )
                b["qty"] -= close_qty
                if b["qty"] <= 1e-9:
                    b["qty"] = 0.0
                    b["avg"] = 0.0
                    b["open_date"] = None
    closed.reverse()  # newest first
    return closed


def _sharpe(snaps) -> float:
    if len(snaps) < 2:
        return 0.0
    rets = [s.daily_pnl_pct for s in snaps[1:]]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / n
    std = math.sqrt(var) if var > 0 else 0.0
    return (mean / std) * math.sqrt(252) if std > 0 else 0.0


def _max_drawdown(snaps) -> float:
    if not snaps:
        return 0.0
    peak = snaps[0].total_value
    mdd = 0.0
    for s in snaps:
        if s.total_value > peak:
            peak = s.total_value
        dd = (peak - s.total_value) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)
    return mdd


def performance(orders, snapshots, current_equity: Optional[float] = None) -> dict:
    closed = closed_positions(orders)
    wins = [c for c in closed if c["realized_pnl"] > 0]
    losses = [c for c in closed if c["realized_pnl"] <= 0]
    total = len(closed)
    gross_profit = sum(c["realized_pnl"] for c in wins)
    gross_loss = abs(sum(c["realized_pnl"] for c in losses))

    cur = current_equity
    if cur is None:
        cur = snapshots[-1].total_value if snapshots else 0.0
    start = snapshots[0].total_value if snapshots else cur

    return {
        "total_trades": total,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / total if total else 0.0,
        "total_realized_pnl": sum(c["realized_pnl"] for c in closed),
        "avg_win": gross_profit / len(wins) if wins else 0.0,
        "avg_loss": (-gross_loss / len(losses)) if losses else 0.0,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "sharpe_ratio": _sharpe(snapshots),
        "max_drawdown": _max_drawdown(snapshots),
        "current_equity": cur,
        "starting_equity": start,
        "total_return_pct": (cur - start) / start if start else 0.0,
        "equity_curve": [
            {
                "date": s.snapshot_date.isoformat(),
                "total_value": s.total_value,
                "cash": s.cash,
                "invested_value": s.invested_value,
                "daily_pnl": s.daily_pnl,
                "daily_pnl_pct": s.daily_pnl_pct,
                "open_positions": s.open_positions,
            }
            for s in snapshots
        ],
    }
