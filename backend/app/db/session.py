"""Database engine and session factory.

The engine is created on first use, not at import time, so unit tests and
tooling can import the app without a database.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(
    url: str, *, pool_size: int = 3, max_overflow: int = 2, connect_timeout_s: int = 5
) -> Engine:
    """Create an engine tuned for a small instance behind the Supabase pooler.

    `prepare_threshold=None` turns off psycopg's server-side prepared
    statements. The Supabase transaction pooler does not support them, and the
    cost of turning them off is negligible at this scale.
    """
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": connect_timeout_s, "prepare_threshold": None},
    )


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return build_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_timeout_s=settings.db_connect_timeout_s,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def check_database(session: Session) -> bool:
    """Return True when a trivial query succeeds."""
    session.execute(text("SELECT 1"))
    return True
