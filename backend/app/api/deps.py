"""Shared FastAPI dependencies: database, storage, model client, user, rate limits."""

import math
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.ratelimit import RateLimiter, login_limiter, upload_limiter
from app.core.security import AuthNotConfiguredError, InvalidTokenError, read_token
from app.extract.llm import LlmClient, get_llm_client
from app.storage import FileStorage
from app.storage import get_storage as build_storage

bearer = HTTPBearer(auto_error=False)


@lru_cache
def _storage() -> FileStorage:
    return build_storage(get_settings())


def get_storage() -> FileStorage:
    return _storage()


@lru_cache
def _llm() -> LlmClient | None:
    settings = get_settings()
    return get_llm_client(settings) if settings.gemini_api_key else None


def get_llm() -> LlmClient | None:
    return _llm()


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return read_token(credentials.credentials, settings)
    except AuthNotConfiguredError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "login is not configured"
        ) from None
    except InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so this is the caller's address behind Render.
    return request.client.host if request.client else "unknown"


def _limit(limiter: RateLimiter, request: Request, limit: int) -> None:
    wait = limiter.hit(client_ip(request), limit)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many requests, try again shortly",
            headers={"Retry-After": str(math.ceil(wait) or 1)},
        )


def limit_login(request: Request, settings: Settings = Depends(get_settings)) -> None:
    _limit(login_limiter, request, settings.login_rate_per_minute)


def limit_upload(request: Request, settings: Settings = Depends(get_settings)) -> None:
    _limit(upload_limiter, request, settings.upload_rate_per_minute)
