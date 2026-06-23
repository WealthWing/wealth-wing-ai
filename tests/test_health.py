from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from main import create_app
from src.config import Settings
from src.error_handlers import register_error_handlers
from src.middleware.request_logging import RequestLoggingMiddleware
from src.services import health as health_service


def _assert_error_response(response, status_code, detail):
    body = response.json()

    assert response.status_code == status_code
    assert body["detail"] == detail
    assert body["request_id"]


def make_client(**settings_overrides):
    settings_values = {
        "ALLOWED_HOSTS": "testserver",
        "COGNITO_JWKS_URL": "",
        "COGNITO_USER_POOL_ID": "",
        "AWS_REGION": "",
        "COGNITO_ISSUER": "",
        "COGNITO_CLIENT_ID": "",
        "TOGETHER_API_KEY": "",
        "WEALTH_WING_DATA_HEALTH_URL": None,
    }
    settings_values.update(settings_overrides)
    settings = Settings(**settings_values)
    return TestClient(create_app(settings))


def test_health_ping_is_public():
    client = make_client()

    response = client.get("/health/ping")

    assert response.status_code == 200
    assert response.json() == {"message": "healthy"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]


def test_health_reports_all_providers(monkeypatch):
    checked_urls = []

    async def healthy_ping(url):
        checked_urls.append(url)
        return True

    monkeypatch.setattr(health_service, "_ping_health_url", healthy_ping)
    client = make_client(
        TOGETHER_API_KEY="test-key",
        WEALTH_WING_DATA_HEALTH_URL="http://127.0.0.1:8000/health/ping",
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "providers": {
            "together": {"status": "healthy"},
            "wealth-wing-data": {"status": "healthy"},
        },
    }
    assert checked_urls == ["http://127.0.0.1:8000/health/ping"]


def test_health_reports_unhealthy_provider_without_leaking_details():
    client = make_client(TOGETHER_API_KEY="")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "providers": {
            "together": {"status": "unhealthy", "reason": "not_configured"},
            "wealth-wing-data": {"status": "unhealthy", "reason": "not_configured"},
        },
    }


def test_request_id_header_is_preserved():
    client = make_client()

    response = client.get("/health/ping", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request"


def test_non_public_routes_require_authentication():
    client = make_client()

    response = client.get("/not-public")

    _assert_error_response(response, 401, "Unauthorized")


def test_public_health_does_not_match_entire_health_prefix():
    client = make_client()

    response = client.get("/health/private")

    _assert_error_response(response, 401, "Unauthorized")


def test_protected_route_with_token_fails_closed_when_auth_is_not_configured():
    client = make_client()

    response = client.get("/not-public", headers={"Authorization": "Bearer token"})

    _assert_error_response(response, 503, "Authentication service unavailable")


def test_docs_are_disabled_by_default():
    client = make_client()

    response = client.get("/docs")

    _assert_error_response(response, 401, "Unauthorized")


def test_docs_can_be_enabled_explicitly():
    client = make_client(ENABLE_DOCS=True)

    response = client.get("/docs")

    assert response.status_code == 200


def test_http_exception_handler_returns_consistent_shape():
    app = _error_test_app()

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(status_code=418, detail="Short and stout")

    client = TestClient(app)

    response = client.get("/http-error")

    _assert_error_response(response, 418, "Short and stout")


def test_validation_error_handler_does_not_echo_input_values():
    app = _error_test_app()

    @app.get("/items/{item_id}")
    async def item(item_id: int):
        return {"item_id": item_id}

    client = TestClient(app)

    response = client.get("/items/not-an-int")
    body = response.json()

    assert response.status_code == 422
    assert body["detail"] == "Validation error"
    assert body["request_id"]
    assert body["errors"][0]["loc"] == ["path", "item_id"]
    assert "input" not in body["errors"][0]


def test_unhandled_exception_handler_hides_internal_details():
    app = _error_test_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("sensitive provider detail")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom")

    _assert_error_response(response, 500, "Internal server error")
    assert "sensitive provider detail" not in response.text


def _error_test_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestLoggingMiddleware, settings=Settings())
    return app
