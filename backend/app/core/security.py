"""Login for the single demo account and JWT bearer tokens (D14).

The password check uses a constant-time comparison. Tokens are HS256, signed
with JWT_SECRET, and expire after JWT_TTL_MINUTES. Without JWT_SECRET or
DEMO_PASSWORD, login is switched off rather than open.
"""

import hmac
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

ISSUER = "docintel"
ALGORITHM = "HS256"


class AuthNotConfiguredError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


def _secret(settings: Settings) -> str:
    if settings.jwt_secret is None or not settings.jwt_secret.get_secret_value():
        raise AuthNotConfiguredError("JWT_SECRET is not set")
    return settings.jwt_secret.get_secret_value()


def check_login(username: str, password: str, settings: Settings) -> bool:
    if settings.demo_password is None or not settings.demo_password.get_secret_value():
        raise AuthNotConfiguredError("DEMO_PASSWORD is not set")
    user_ok = hmac.compare_digest(username.encode(), settings.demo_username.encode())
    pass_ok = hmac.compare_digest(
        password.encode(), settings.demo_password.get_secret_value().encode()
    )
    return user_ok and pass_ok


def create_token(username: str, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.jwt_ttl_minutes)
    claims = {"sub": username, "iss": ISSUER, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, _secret(settings), algorithm=ALGORITHM), int(ttl.total_seconds())


def read_token(token: str, settings: Settings) -> str:
    """Return the username in a valid token."""
    try:
        claims = jwt.decode(
            token,
            _secret(settings),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError:
        raise InvalidTokenError("invalid or expired token") from None
    return str(claims["sub"])
