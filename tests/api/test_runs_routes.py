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
        queue_enabled=False,
    )
    return TestClient(create_app(config))


def test_create_and_list_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = make_client(tmp_path)
    headers = {"Authorization": "Bearer test-token"}

    response = client.post(
        "/api/runs",
        headers=headers,
        json={
            "ticker": "spy",
            "analysis_date": "2026-05-19",
            "asset_type": "stock",
            "analysts": ["market", "news"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_think_llm": "gpt-5.4-mini",
            "deep_think_llm": "gpt-5.4",
            "output_language": "English",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["ticker"] == "SPY"
    assert created["status"] == "queued"

    listed = client.get("/api/runs", headers=headers).json()
    assert listed["runs"][0]["id"] == created["id"]
