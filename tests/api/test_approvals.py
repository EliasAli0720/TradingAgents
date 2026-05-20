from tradingagents.api.db import init_api_schema
from tradingagents.api.repositories import ApprovalRepository


def test_approval_requires_exact_confirmation(tmp_path):
    db_path = str(tmp_path / "api.db")
    init_api_schema(db_path)
    approvals = ApprovalRepository(db_path)
    proposal = approvals.create(
        run_id="run_1",
        ticker="AAPL",
        signal="Buy",
        side="buy",
        quantity=1.0,
        estimated_price=100.0,
        reasoning="test",
    )

    try:
        approvals.approve(proposal["id"], confirmation="APPROVE MSFT", actor="session:test")
    except ValueError as exc:
        assert "APPROVE AAPL" in str(exc)
    else:
        raise AssertionError("approval should have failed")

    approved = approvals.approve(proposal["id"], confirmation="APPROVE AAPL", actor="session:test")
    assert approved["status"] == "approved"
