"""Health endpoints.

`/api/health/live` answers without touching the database. Render uses it as
the service health check, so a paused Supabase project cannot fail a deploy.

`/api/health` also runs `SELECT 1`. The frontend calls it to show
"API healthy, database connected" (DECISIONS.md D23).
"""

import logging
import time
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings, get_settings
from app.db.session import check_database, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["connected", "unavailable"]
    database_latency_ms: float | None
    environment: str
    version: str


@router.get("/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(status="ok", version=__version__)


@router.get(
    "",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
)
def health(
    response: Response,
    db: Session = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> HealthResponse:
    started = time.perf_counter()
    try:
        check_database(db)
    except Exception as exc:  # any driver or network error means "unavailable"
        # Log the error type only; driver messages can contain the host name.
        logger.warning("health check: database unavailable (%s)", type(exc).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degraded",
            database="unavailable",
            database_latency_ms=None,
            environment=settings.app_env,
            version=__version__,
        )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return HealthResponse(
        status="ok",
        database="connected",
        database_latency_ms=latency_ms,
        environment=settings.app_env,
        version=__version__,
    )
