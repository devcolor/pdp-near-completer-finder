from fastapi.testclient import TestClient

from app.main import app


def test_unknown_endpoint_returns_json_error_with_docs_hint(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "status": 404,
            "code": "not_found",
            "message": "No endpoint matches GET /api/v1/does-not-exist.",
            "path": "/api/v1/does-not-exist",
            "docs": "/docs",
        }
    }


def test_http_exception_keeps_its_own_message(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard?credit_threshold=1")

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Unsupported credit threshold."
    assert "docs" not in response.json()["error"]


def test_validation_errors_list_each_field(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard?hold=maybe")

    error = response.json()["error"]
    assert response.status_code == 422
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["query", "hold"]


def test_wrong_method_returns_405(client: TestClient) -> None:
    response = client.delete("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_unexpected_errors_hide_details() -> None:
    @app.get("/api/v1/_boom", include_in_schema=False)
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/_boom")
    finally:
        app.router.routes = [
            route for route in app.router.routes if getattr(route, "path", "") != "/api/v1/_boom"
        ]

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text


def test_a_crash_still_carries_cors_headers(monkeypatch) -> None:
    """A 500 must reach the browser, or it reports "could not reach the API" instead."""
    from app.core.config import settings
    from app.main import create_app

    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://ui.example"])
    crashing = create_app()

    @crashing.get("/boom")
    async def boom() -> None:
        raise OSError("Read-only file system")

    response = TestClient(crashing, raise_server_exceptions=False).get(
        "/boom", headers={"Origin": "https://ui.example"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.headers["access-control-allow-origin"] == "https://ui.example"
