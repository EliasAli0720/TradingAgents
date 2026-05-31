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
    def generate(self, *, watchlist, recent_context, today):
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


def test_generate_requires_watchlist():
    client = _client()
    _login(client)
    _put_model_settings(client)

    response = client.post("/recommendations/generate", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "watchlist not configured"


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
