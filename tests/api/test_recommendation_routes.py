from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session
from tradingagents.api.recommendation_service import RecommendationCandidate


def _client() -> TestClient:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app)


def _login(client: TestClient) -> str:
    client.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "hunter22a"},
    )
    assert response.status_code == 200
    csrf = client.cookies.get("tradingagents_csrf")
    client.headers.update({"X-CSRF-Token": csrf})
    return csrf


def _put_model_settings(client: TestClient) -> None:
    response = client.put(
        "/settings/model",
        json={
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
        },
    )
    assert response.status_code == 200


def test_watchlist_requires_authentication():
    client = _client()

    response = client.get("/recommendations/watchlist")

    assert response.status_code == 401


def test_watchlist_get_put_roundtrip():
    client = _client()
    csrf = _login(client)

    before_save = client.get("/recommendations/watchlist")

    assert before_save.status_code == 200
    assert before_save.json() == {"tickers": [], "updated_at": None}

    saved = client.put(
        "/recommendations/watchlist",
        json={"tickers": [" nvda ", "AAPL", "nvda"]},
        headers={"X-CSRF-Token": csrf},
    )

    assert saved.status_code == 200
    saved_body = saved.json()
    assert saved_body["tickers"] == ["NVDA", "AAPL"]
    assert saved_body["updated_at"] is not None

    fetched = client.get("/recommendations/watchlist")

    assert fetched.status_code == 200
    assert fetched.json() == saved_body


def test_watchlist_rejects_invalid_ticker():
    client = _client()
    csrf = _login(client)

    response = client.put(
        "/recommendations/watchlist",
        json={"tickers": ["AAPL", "../BAD"]},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422


class FakeGenerator:
    def generate(self, *, watchlist, recent_context, today, language=None):
        assert watchlist == ["NVDA", "AAPL"]
        return [
            RecommendationCandidate(
                ticker="NVDA",
                source="watchlist",
                priority=1,
                reason="AI infrastructure leader",
                risk="Valuation sensitivity",
            ),
            RecommendationCandidate(
                ticker="MSFT",
                source="model_expansion",
                priority=2,
                reason="Cloud and enterprise AI exposure",
                risk="Large-cap multiple risk",
            ),
        ]


def test_generate_requires_model_settings():
    client = _client()
    _login(client)
    client.put("/recommendations/watchlist", json={"tickers": ["NVDA", "AAPL"]})

    response = client.post("/recommendations/generate", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "model settings not configured"


class FakeFullMarketGenerator:
    """Generator used when no watchlist is set — recommends across the market."""

    def generate(self, *, watchlist, recent_context, today, language=None):
        assert watchlist == []  # empty pool → full-market mode
        return [
            RecommendationCandidate(
                ticker="NVDA",
                source="model_expansion",
                priority=1,
                reason="Broad-market momentum",
                risk="Valuation sensitivity",
            ),
        ]


def test_generate_without_watchlist_uses_model_expansion(monkeypatch):
    client = _client()
    _login(client)
    _put_model_settings(client)  # model configured, but no watchlist saved

    from tradingagents.api.routers import recommendations

    monkeypatch.setattr(
        recommendations,
        "build_recommendation_generator",
        lambda settings: FakeFullMarketGenerator(),
    )

    response = client.post("/recommendations/generate", json={})

    assert response.status_code == 200
    body = response.json()
    assert [item["ticker"] for item in body["items"]] == ["NVDA"]
    assert body["items"][0]["source"] == "model_expansion"


def test_generate_saves_batch_and_history(monkeypatch):
    client = _client()
    _login(client)
    _put_model_settings(client)
    client.put("/recommendations/watchlist", json={"tickers": ["NVDA", "AAPL"]})

    from tradingagents.api.routers import recommendations

    monkeypatch.setattr(
        recommendations,
        "build_recommendation_generator",
        lambda settings: FakeGenerator(),
    )

    response = client.post("/recommendations/generate", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"].startswith("rec_")
    assert [item["ticker"] for item in body["items"]] == ["NVDA", "MSFT"]
    assert body["items"][1]["source"] == "model_expansion"

    batches = client.get("/recommendations/batches")
    assert batches.status_code == 200
    assert batches.json()[0]["batch_id"] == body["batch_id"]
    assert batches.json()[0]["item_count"] == 2

    detail = client.get(f"/recommendations/batches/{body['batch_id']}")
    assert detail.status_code == 200
    assert detail.json()["items"][0]["reason"] == "AI infrastructure leader"


def test_analyze_selected_items_creates_default_stock_runs(monkeypatch):
    client = _client()
    _login(client)
    _put_model_settings(client)
    client.put("/recommendations/watchlist", json={"tickers": ["NVDA", "AAPL"]})

    from tradingagents.api.routers import recommendations

    monkeypatch.setattr(
        recommendations,
        "build_recommendation_generator",
        lambda settings: FakeGenerator(),
    )
    batch = client.post("/recommendations/generate", json={}).json()
    item_id = batch["items"][0]["item_id"]

    response = client.post(
        f"/recommendations/batches/{batch['batch_id']}/analyze",
        json={"item_ids": [item_id]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["failed"] == []
    assert body["created"][0]["item_id"] == item_id
    assert body["created"][0]["ticker"] == "NVDA"
    assert body["created"][0]["run_id"].startswith("run_")

    refreshed = client.get(f"/recommendations/batches/{batch['batch_id']}").json()
    item = refreshed["items"][0]
    assert item["status"] == "analysis_queued"
    assert item["run_id"] == body["created"][0]["run_id"]

    run = client.get(f"/runs/{item['run_id']}").json()
    assert run["ticker"] == "NVDA"
    assert run["asset_type"] == "stock"
    assert run["analysts"] == ["market", "social", "news", "fundamentals"]


def test_batch_reflects_run_status_and_allows_reanalysis(monkeypatch):
    client = _client()
    _login(client)
    _put_model_settings(client)
    client.put("/recommendations/watchlist", json={"tickers": ["NVDA", "AAPL"]})

    from tradingagents.api.routers import recommendations

    monkeypatch.setattr(
        recommendations,
        "build_recommendation_generator",
        lambda settings: FakeGenerator(),
    )
    batch = client.post("/recommendations/generate", json={}).json()
    batch_id = batch["batch_id"]
    item_id = batch["items"][0]["item_id"]

    first = client.post(
        f"/recommendations/batches/{batch_id}/analyze",
        json={"item_ids": [item_id]},
    ).json()
    first_run_id = first["created"][0]["run_id"]

    # Simulate the run terminating without success (cancel == terminal state).
    assert client.post(f"/runs/{first_run_id}/cancel").status_code == 200

    # The batch now reflects the live run status and marks the item retryable.
    refreshed = client.get(f"/recommendations/batches/{batch_id}").json()
    item = refreshed["items"][0]
    assert item["run_status"] == "cancelled"
    assert item["status"] == "analysis_failed"

    # Re-analyzing the failed item is allowed and starts a fresh run.
    retry = client.post(
        f"/recommendations/batches/{batch_id}/analyze",
        json={"item_ids": [item_id]},
    ).json()
    assert retry["failed"] == []
    assert retry["created"][0]["item_id"] == item_id
    new_run_id = retry["created"][0]["run_id"]
    assert new_run_id != first_run_id

    after = client.get(f"/recommendations/batches/{batch_id}").json()["items"][0]
    assert after["status"] == "analysis_queued"
    assert after["run_id"] == new_run_id
