"""Health endpoints.

`/api/health/live` answers without touching the database. Render uses it as
the service health check, so a paused Supabase project cannot fail a deploy.

`/api/health` also runs `SELECT 1` and asks file storage to list one object,
so a wrong storage key shows up here without signing in (D32). The frontend
calls it to show whether the server is ready (DECISIONS.md D24).
"""

import logging
import time
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import get_storage
from app.core.config import Settings, get_settings
from app.db.session import check_database, get_db
from app.storage import FileStorage, StorageError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

# /api/health needs no sign-in, so its storage result is reused for a short
# while: a flood of health requests must not become a flood of Storage calls.
STORAGE_CHECK_TTL_S = 15.0
_storage_cache: dict[int, tuple[float, Literal["ok", "error"]]] = {}


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["connected", "unavailable"]
    database_latency_ms: float | None
    storage: Literal["ok", "error"]
    environment: str
    version: str


@router.get("/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(status="ok", version=__version__)


@router.get(
    "",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database or storage unavailable"}},
)
def health(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    started = time.perf_counter()
    database: Literal["connected", "unavailable"] = "connected"
    latency_ms: float | None = None
    try:
        check_database(db)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
    except Exception as exc:  # any driver or network error means "unavailable"
        # Log the error type only; driver messages can contain the host name.
        logger.warning("health check: database unavailable (%s)", type(exc).__name__)
        database = "unavailable"
    storage = check_storage(request)
    healthy = database == "connected" and storage == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if healthy else "degraded",
        database=database,
        database_latency_ms=latency_ms,
        storage=storage,
        environment=settings.app_env,
        version=__version__,
    )


def check_storage(request: Request) -> Literal["ok", "error"]:
    """Ask the file store to list one object. Never raises.

    The store is built here, not through Depends, so a missing setting reads as
    "error" instead of a 500. Test overrides of get_storage still apply.
    """
    try:
        provider = request.app.dependency_overrides.get(get_storage, get_storage)
        store: FileStorage = provider()
    except Exception as exc:  # a missing setting
        logger.warning("health check: storage not configured (%s)", type(exc).__name__)
        return "error"
    now = time.monotonic()
    cached = _storage_cache.get(id(store))
    if cached and now - cached[0] < STORAGE_CHECK_TTL_S:
        return cached[1]
    result: Literal["ok", "error"] = "ok"
    try:
        store.check()
    except StorageError as exc:
        # StorageError messages hold the status and Storage's error code, never the key.
        logger.warning("health check: storage error (%s)", exc)
        result = "error"
    except Exception as exc:
        logger.warning("health check: storage error (%s)", type(exc).__name__)
        result = "error"
    _storage_cache.clear()  # one store per process; keep only the latest answer
    _storage_cache[id(store)] = (now, result)
    return result
