"""Shared test setup.

Unit tests never touch the network or a database. Integration tests need a
PostgreSQL database with pgvector, given by TEST_DATABASE_URL; without it they
are skipped. Tests marked `tesseract` need the OCR binary; they skip without
it, unless REQUIRE_TESSERACT=1 (set in CI), where a missing binary fails.
Phase 2 adds the fake LLM client here.
"""

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

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


HAVE_TESSERACT = shutil.which("tesseract") is not None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if HAVE_TESSERACT or os.environ.get("REQUIRE_TESSERACT") == "1":
        return
    skip = pytest.mark.skip(reason="tesseract is not installed")
    for item in items:
        if "tesseract" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The small synthetic dataset (eval/generate), built once per test run."""
    from synth.dataset import build

    out = tmp_path_factory.mktemp("synthetic")
    build(out, seed=7, scale=1)
    return out


@pytest.fixture(scope="session")
def manifest(synthetic_dir: Path) -> list[dict]:
    return json.loads((synthetic_dir / "manifest.json").read_text())
