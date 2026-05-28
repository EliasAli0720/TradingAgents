from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from tradingagents.api.artifacts import ArtifactWrite, LocalArtifactStore
from tradingagents.dataflows.utils import safe_ticker_component


def save_analysis_report(
    final_state: dict[str, Any],
    ticker: str,
    reports_root: str | Path,
    *,
    generated_at: datetime | None = None,
    run_id: str | None = None,
    artifact_store: LocalArtifactStore | None = None,
) -> Path | list[ArtifactWrite]:
    """Save a complete analysis report to disk with organized subfolders."""
    generated_at = generated_at or datetime.now()
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    artifacts: list[ArtifactWrite] = []
    if artifact_store is None or run_id is None:
        save_path = Path(reports_root) / f"{safe_ticker_component(ticker).upper()}_{timestamp}"
        save_path.mkdir(parents=True, exist_ok=True)
        write_markdown: Callable[[str, str], Path | ArtifactWrite] = (
            lambda relative_path, content: _write_file(save_path, relative_path, content)
        )
    else:
        write_markdown = lambda relative_path, content: _write_artifact(
            artifact_store,
            artifacts,
            run_id,
            relative_path,
            content,
        )
    sections: list[str] = []

    analyst_parts: list[tuple[str, str]] = []
    _write_optional(
        write_markdown,
        "1_analysts/market.md",
        final_state.get("market_report"),
        analyst_parts,
        "Market Analyst",
    )
    _write_optional(
        write_markdown,
        "1_analysts/sentiment.md",
        final_state.get("sentiment_report"),
        analyst_parts,
        "Sentiment Analyst",
    )
    _write_optional(
        write_markdown,
        "1_analysts/news.md",
        final_state.get("news_report"),
        analyst_parts,
        "News Analyst",
    )
    _write_optional(
        write_markdown,
        "1_analysts/fundamentals.md",
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
    research_parts: list[tuple[str, str]] = []
    _write_optional(
        write_markdown,
        "2_research/bull.md",
        debate.get("bull_history"),
        research_parts,
        "Bull Researcher",
    )
    _write_optional(
        write_markdown,
        "2_research/bear.md",
        debate.get("bear_history"),
        research_parts,
        "Bear Researcher",
    )
    _write_optional(
        write_markdown,
        "2_research/manager.md",
        debate.get("judge_decision") or final_state.get("investment_plan"),
        research_parts,
        "Research Manager",
    )
    if research_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
        sections.append(f"## II. Research Team Decision\n\n{content}")

    trader_plan = _text(final_state.get("trader_investment_plan"))
    if trader_plan:
        write_markdown("3_trading/trader.md", trader_plan)
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{trader_plan}")

    risk = final_state.get("risk_debate_state")
    if not isinstance(risk, dict):
        risk = {}
    risk_parts: list[tuple[str, str]] = []
    _write_optional(
        write_markdown,
        "4_risk/aggressive.md",
        risk.get("aggressive_history"),
        risk_parts,
        "Aggressive Analyst",
    )
    _write_optional(
        write_markdown,
        "4_risk/conservative.md",
        risk.get("conservative_history"),
        risk_parts,
        "Conservative Analyst",
    )
    _write_optional(
        write_markdown,
        "4_risk/neutral.md",
        risk.get("neutral_history"),
        risk_parts,
        "Neutral Analyst",
    )
    if risk_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
        sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

    portfolio_decision = _text(risk.get("judge_decision") or final_state.get("final_trade_decision"))
    if portfolio_decision:
        write_markdown("5_portfolio/decision.md", portfolio_decision)
        sections.append(
            f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{portfolio_decision}"
        )

    header = (
        f"# Trading Analysis Report: {safe_ticker_component(ticker).upper()}\n\n"
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    complete_report = write_markdown("complete_report.md", header + "\n\n".join(sections))
    if artifact_store is not None and run_id is not None:
        return artifacts
    return complete_report


def _write_optional(
    write_markdown: Callable[[str, str], Path | ArtifactWrite],
    relative_path: str,
    value: Any,
    parts: list[tuple[str, str]],
    label: str,
) -> None:
    text = _text(value)
    if not text:
        return
    write_markdown(relative_path, text)
    parts.append((label, text))


def _text(value: Any) -> str:
    return value if isinstance(value, str) and value else ""


def _write_file(save_path: Path, relative_path: str, content: str) -> Path:
    path = save_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_artifact(
    artifact_store: LocalArtifactStore,
    artifacts: list[ArtifactWrite],
    run_id: str,
    relative_path: str,
    content: str,
) -> ArtifactWrite:
    artifact = artifact_store.write_text(
        run_id=run_id,
        kind="report_md",
        relative_path=f"reports/{relative_path}",
        content=content,
        content_type="text/markdown",
    )
    artifacts.append(artifact)
    return artifact
