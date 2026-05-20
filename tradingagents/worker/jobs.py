from __future__ import annotations

from tradingagents.api.repositories import RunEventRepository, RunRepository


def run_fake_analysis(run_id: str, db_path: str) -> None:
    runs = RunRepository(db_path)
    events = RunEventRepository(db_path)
    runs.update_status(run_id, "running")
    events.append(run_id, "agent_status", {"agent": "Market Analyst", "status": "running"})
    events.append(run_id, "message", {"type": "System", "content": "Fake analysis started"})
    events.append(
        run_id,
        "report_section",
        {"section": "market_report", "content": "Fake market report for local development."},
    )
    runs.update_status(run_id, "completed", result={"final_trade_decision": "Rating: Hold"})
    events.append(run_id, "completed", {"signal": "Hold"})
