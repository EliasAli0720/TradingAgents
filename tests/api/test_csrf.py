from fastapi import FastAPI
from fastapi.testclient import TestClient

from tradingagents.api.middleware import CsrfMiddleware


def _make_client(exempt: tuple[str, ...] = ()) -> TestClient:
    app = FastAPI()
    app.add_middleware(CsrfMiddleware, csrf_cookie_name="csrf", exempt_paths=exempt)

    @app.get("/r")
    def read():
        return {"ok": True}

    @app.post("/r")
    def write():
        return {"ok": True}

    return TestClient(app)


def test_get_skips_csrf():
    client = _make_client()
    assert client.get("/r").status_code == 200


def test_post_without_csrf_cookie_blocked():
    client = _make_client()
    assert client.post("/r", headers={"X-CSRF-Token": "abc"}).status_code == 403


def test_post_without_csrf_header_blocked():
    client = _make_client()
    client.cookies.set("csrf", "abc")
    assert client.post("/r").status_code == 403


def test_post_with_mismatched_csrf_blocked():
    client = _make_client()
    client.cookies.set("csrf", "abc")
    assert client.post("/r", headers={"X-CSRF-Token": "xyz"}).status_code == 403


def test_post_with_matching_csrf_allowed():
    client = _make_client()
    client.cookies.set("csrf", "abc")
    assert client.post("/r", headers={"X-CSRF-Token": "abc"}).status_code == 200


def test_exempt_path_skips_csrf():
    client = _make_client(exempt=("/r",))
    assert client.post("/r").status_code == 200
