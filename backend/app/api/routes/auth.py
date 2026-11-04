"""POST /api/auth/login: the single demo account (D14)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import limit_login
from app.api.schemas import LoginRequest, TokenResponse
from app.core.config import Settings, get_settings
from app.core.security import AuthNotConfiguredError, check_login, create_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(limit_login)],
    responses={401: {"description": "Wrong username or password"}, 429: {}, 503: {}},
)
def login(body: LoginRequest, settings: Settings = Depends(get_settings)) -> TokenResponse:
    try:
        ok = check_login(body.username, body.password, settings)
        if not ok:
            logger.info("login failed")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong username or password")
        token, expires_in = create_token(body.username, settings)
    except AuthNotConfiguredError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "login is not configured"
        ) from None
    return TokenResponse(access_token=token, expires_in=expires_in)
