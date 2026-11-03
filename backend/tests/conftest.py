"""Shared test setup.

Unit tests never touch the network or a database. Integration tests need a
PostgreSQL database with pgvector, given by TEST_DATABASE_URL; without it they
are skipped. Phase 2 adds the fake LLM client here.
"""

import os
from collections.abc import Iterator

import pytest

# Tests must never pick up a developer's real .env values.
os.environ["APP_ENV"] = "test"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from app.core.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """Each test reads settings from the environment it set up."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
