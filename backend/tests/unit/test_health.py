from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app


class FakeSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        if self.error:
            raise self.error


def make_client(session: FakeSession) -> TestClient:
    app = create_app(Settings(_env_file=None, cors_origins="https://front.example"))

    def _db() -> Iterator[FakeSession]:
        yield session

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_live_never_needs_the_database() -> None:
    client = make_client(FakeSession(error=RuntimeError("must not be called")))
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_connected_database() -> None:
    response = make_client(FakeSession()).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["database_latency_ms"] >= 0


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, Exception("could not connect to secret-host.example")),
        TimeoutError("timed out"),
    ],
)
def test_health_returns_503_without_leaking_details(error: Exception) -> None:
    response = make_client(FakeSession(error=error)).get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    assert "secret-host" not in response.text


def test_cors_allows_only_the_configured_origin() -> None:
    client = make_client(FakeSession())
    allowed = client.get("/api/health/live", headers={"Origin": "https://front.example"})
    assert allowed.headers.get("access-control-allow-origin") == "https://front.example"

    blocked = client.get("/api/health/live", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


def test_openapi_docs_are_served_under_api() -> None:
    client = make_client(FakeSession())
    assert client.get("/api/openapi.json").status_code == 200
    assert client.get("/api/docs").status_code == 200


def test_every_response_carries_security_headers() -> None:
    client = make_client(FakeSession())
    for path in ("/api/health/live", "/api/documents"):  # an answer and a 401
        headers = client.get(path).headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["cache-control"] == "no-store"
        assert headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
        assert "strict-transport-security" not in headers  # only in production
    docs = client.get("/api/docs").headers
    assert "content-security-policy" not in docs  # Swagger UI needs its scripts
