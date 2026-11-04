"""Shared test setup.

Unit tests never touch the network or a database. Integration tests need a
PostgreSQL database with pgvector, given by TEST_DATABASE_URL; without it they
are skipped. Tests marked `tesseract` need the OCR binary; they skip without
it, unless REQUIRE_TESSERACT=1 (set in CI), where a missing binary fails.
`FakeLlmClient` stands in for Gemini in every unit test.
"""

import json
import os
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

# Tests must never pick up a developer's real .env values.
os.environ["APP_ENV"] = "test"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from pydantic import BaseModel  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.extract.breaker import BREAKER  # noqa: E402
from app.extract.llm import LlmReply, LlmUsage, Turn  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """Each test reads settings from the environment it set up, and starts with
    no model marked as failing (D67)."""
    get_settings.cache_clear()
    BREAKER.reset()
    yield
    get_settings.cache_clear()
    BREAKER.reset()


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


@dataclass
class FakeCall:
    purpose: str
    model: str
    system: str
    turns: list[Turn]
    schema: type[BaseModel] | None


Responder = Callable[[FakeCall], str | dict | BaseModel]


def fake_vector(text: str, dim: int) -> list[float]:
    import hashlib
    import math
    import re

    vector = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) > 2:  # skip the "|" prefixes and tiny words
            index = int(hashlib.sha256(word.encode()).hexdigest(), 16) % dim
            vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


@dataclass
class FakeLlmClient:
    """Answers like Gemini without the network.

    Give it a list of replies (used in order) or a function of the call. A dict
    or model reply is sent as JSON. Every call is recorded in `calls`.
    """

    replies: list[str | dict | BaseModel] | Responder = field(default_factory=list)
    calls: list[FakeCall] = field(default_factory=list)
    tokens: tuple[int, int] = (100, 20)
    embedded: list[str] = field(default_factory=list)

    def generate(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        turns: list[Turn],
        schema: type[BaseModel] | None = None,
    ) -> LlmReply:
        call = FakeCall(purpose, model, system, list(turns), schema)
        self.calls.append(call)
        if callable(self.replies):
            reply = self.replies(call)
        else:
            if not self.replies:
                raise AssertionError(f"FakeLlmClient has no reply left for {purpose}")
            reply = self.replies.pop(0)
        if isinstance(reply, BaseModel):
            reply = reply.model_dump_json()
        elif isinstance(reply, dict):
            reply = json.dumps(reply)
        usage = LlmUsage(purpose, model, prompt_tokens=self.tokens[0], output_tokens=self.tokens[1])
        return LlmReply(text=reply, usage=usage)

    def embed(
        self, *, model: str, texts: list[str], dim: int
    ) -> tuple[list[list[float]], LlmUsage]:
        """Bag-of-words vectors: texts that share words point the same way."""
        self.embedded.extend(texts)
        return [fake_vector(t, dim) for t in texts], LlmUsage("embed", model, len(texts), 0)


@pytest.fixture
def fake_llm() -> FakeLlmClient:
    return FakeLlmClient()
