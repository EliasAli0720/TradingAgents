from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def test_manual_trade_requires_auth_and_confirmation(tmp_path):
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    client = TestClient(create_app(config))

    denied = client.post("/api/trades/manual", json={})
    assert denied.status_code == 401

    bad_confirmation = client.post(
        "/api/trades/manual",
        headers={"Authorization": "Bearer test-token"},
        json={"ticker": "AAPL", "side": "buy", "quantity": 1, "confirmation": "BUY"},
    )
    assert bad_confirmation.status_code == 400
