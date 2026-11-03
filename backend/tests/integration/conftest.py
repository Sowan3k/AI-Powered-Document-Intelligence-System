"""Fixtures for tests that need PostgreSQL with pgvector.

Set TEST_DATABASE_URL to a throwaway database whose name contains "test".
These tests drop and recreate every table in it.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import build_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in str(item.path):
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URL:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL is not set"))


def alembic_config(engine: Engine) -> tuple[Config, object]:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "app/db/migrations"))
    connection = engine.connect()
    config.attributes["connection"] = connection
    return config, connection


def run_alembic(engine: Engine, action: str, revision: str) -> None:
    config, connection = alembic_config(engine)
    try:
        getattr(command, action)(config, revision)
        connection.commit()  # type: ignore[attr-defined]
    finally:
        connection.close()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL
    database = make_url(TEST_DATABASE_URL).database or ""
    if "test" not in database:
        pytest.fail(f"refusing to run: database name {database!r} does not contain 'test'")
    eng = build_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=0)
    # Start from an empty schema, then migrate to the latest revision.
    run_alembic(eng, "downgrade", "base")
    run_alembic(eng, "upgrade", "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def table_names(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        return {row[0] for row in rows}
