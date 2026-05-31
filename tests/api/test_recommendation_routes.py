from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tradingagents.api.app import create_app
from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.deps import get_db_session


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
    return client.cookies.get("tradingagents_csrf")


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
