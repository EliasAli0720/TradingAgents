from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from tradingagents.dataflows.utils import safe_ticker_component


def save_analysis_report(
    final_state: dict[str, Any],
    ticker: str,
    reports_root: str | Path,
    *,
    generated_at: datetime | None = None,
) -> Path:
    """Save a complete analysis report to disk with organized subfolders."""
    generated_at = generated_at or datetime.now()
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    save_path = Path(reports_root) / f"{safe_ticker_component(ticker).upper()}_{timestamp}"
    save_path.mkdir(parents=True, exist_ok=True)
    sections: list[str] = []

    analysts_dir = save_path / "1_analysts"
    analyst_parts: list[tuple[str, str]] = []
    _write_optional(analysts_dir, "market.md", final_state.get("market_report"), analyst_parts, "Market Analyst")
    _write_optional(analysts_dir, "sentiment.md", final_state.get("sentiment_report"), analyst_parts, "Sentiment Analyst")
    _write_optional(analysts_dir, "news.md", final_state.get("news_report"), analyst_parts, "News Analyst")
    _write_optional(
        analysts_dir,
        "fundamentals.md",
        final_state.get("fundamentals_report"),
        analyst_parts,
        "Fundamentals Analyst",
    )
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    debate = final_state.get("investment_debate_state")
    if not isinstance(debate, dict):
        debate = {}
    research_dir = save_path / "2_research"
    research_parts: list[tuple[str, str]] = []
    _write_optional(research_dir, "bull.md", debate.get("bull_history"), research_parts, "Bull Researcher")
    _write_optional(research_dir, "bear.md", debate.get("bear_history"), research_parts, "Bear Researcher")
    _write_optional(
        research_dir,
        "manager.md",
        debate.get("judge_decision") or final_state.get("investment_plan"),
        research_parts,
        "Research Manager",
    )
    if research_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
        sections.append(f"## II. Research Team Decision\n\n{content}")

    trader_plan = _text(final_state.get("trader_investment_plan"))
    if trader_plan:
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(trader_plan, encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{trader_plan}")

    risk = final_state.get("risk_debate_state")
    if not isinstance(risk, dict):
        risk = {}
    risk_dir = save_path / "4_risk"
    risk_parts: list[tuple[str, str]] = []
    _write_optional(risk_dir, "aggressive.md", risk.get("aggressive_history"), risk_parts, "Aggressive Analyst")
    _write_optional(risk_dir, "conservative.md", risk.get("conservative_history"), risk_parts, "Conservative Analyst")
    _write_optional(risk_dir, "neutral.md", risk.get("neutral_history"), risk_parts, "Neutral Analyst")
    if risk_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
        sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

    portfolio_decision = _text(risk.get("judge_decision") or final_state.get("final_trade_decision"))
    if portfolio_decision:
        portfolio_dir = save_path / "5_portfolio"
        portfolio_dir.mkdir(exist_ok=True)
        (portfolio_dir / "decision.md").write_text(portfolio_decision, encoding="utf-8")
        sections.append(
            f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{portfolio_decision}"
        )

    header = (
        f"# Trading Analysis Report: {safe_ticker_component(ticker).upper()}\n\n"
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    complete_report = save_path / "complete_report.md"
    complete_report.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return complete_report


def _write_optional(
    directory: Path,
    file_name: str,
    value: Any,
    parts: list[tuple[str, str]],
    label: str,
) -> None:
    text = _text(value)
    if not text:
        return
    directory.mkdir(exist_ok=True)
    (directory / file_name).write_text(text, encoding="utf-8")
    parts.append((label, text))


def _text(value: Any) -> str:
    return value if isinstance(value, str) and value else ""
