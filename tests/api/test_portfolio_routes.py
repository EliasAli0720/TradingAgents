from fastapi.testclient import TestClient

from tradingagents.api.app import create_app
from tradingagents.api.config import ApiConfig


def make_client(tmp_path):
    config = ApiConfig(
        api_token="test-token",
        redis_url="redis://localhost:6379/0",
        db_path=str(tmp_path / "api.db"),
        results_dir=str(tmp_path / "logs"),
        cors_origins=("http://localhost:5173",),
    )
    return TestClient(create_app(config))


def test_portfolio_account_returns_mock_account(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/portfolio/account", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["cash"] >= 0
    assert body["equity"] >= 0


def test_risk_status_returns_limits(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/risk/status", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert "limits" in response.json()


def test_portfolio_performance_is_json_safe_for_empty_history(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/portfolio/performance", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_trades"] == 0
    assert body["profit_factor"] >= 0
