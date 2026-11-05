from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.deps import get_storage
from app.api.routes import health as health_route
from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.storage import StorageError


class FakeSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        if self.error:
            raise self.error


class FakeStore:
    """Only `check` matters here; it fails the way SupabaseStorage does."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.checks = 0

    def check(self) -> None:
        self.checks += 1
        if self.error:
            raise self.error


@pytest.fixture(autouse=True)
def fresh_storage_cache() -> Iterator[None]:
    health_route._storage_cache.clear()
    yield
    health_route._storage_cache.clear()


def make_client(session: FakeSession, store: object | None = None) -> TestClient:
    app = create_app(Settings(_env_file=None, cors_origins="https://front.example"))

    def _db() -> Iterator[FakeSession]:
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: store if store is not None else FakeStore()
    return TestClient(app)


def test_live_never_needs_the_database() -> None:
    store = FakeStore()
    client = make_client(FakeSession(error=RuntimeError("must not be called")), store)
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert store.checks == 0  # no external call of any kind


def test_health_reports_connected_database() -> None:
    response = make_client(FakeSession()).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["database_latency_ms"] >= 0
    assert body["storage"] == "ok"


def test_health_reports_a_storage_error_without_leaking_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # What production gave on 5 Nov 2026 before the header fix (D32).
    error = StorageError("storage check failed with HTTP 400 (FST_ERR_VALIDATION)")
    response = make_client(FakeSession(), FakeStore(error)).get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "connected"
    assert body["storage"] == "error"
    assert "FST_ERR_VALIDATION" not in response.text  # the code goes to the log only
    assert "FST_ERR_VALIDATION" in caplog.text


def test_health_reports_unconfigured_storage_as_an_error() -> None:
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_db] = lambda: FakeSession()

    def missing() -> None:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    app.dependency_overrides[get_storage] = missing
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json()["storage"] == "error"


def test_health_reuses_a_recent_storage_answer() -> None:
    store = FakeStore()
    client = make_client(FakeSession(), store)
    for _ in range(5):
        assert client.get("/api/health").json()["storage"] == "ok"
    assert store.checks == 1  # an open endpoint must not fan out to Storage


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
    assert body["storage"] == "ok"
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
