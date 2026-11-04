"""The one module that calls Gemini (CLAUDE.md AI rule 5).

`GeminiClient` adds what every call needs: a semaphore that caps calls in
flight, retries with exponential backoff on 429, 5xx and timeouts, a timeout
per call, and one log line per call with token counts and latency. Logs never
hold prompt or response text, because both contain document data.

`generate_structured` validates the reply against a Pydantic schema. An
invalid reply is retried once with the validation error; a second failure
raises `LlmOutputError` (AI rule 4).

Tests use the fake client in `tests/conftest.py`; no unit test calls the network.
"""

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, SecretStr, ValidationError

from app.core.config import Settings
from app.extract import prompts

logger = logging.getLogger(__name__)

RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class LlmError(Exception):
    """A call failed after its retries (network, quota or server). Safe to retry later."""


class LlmOutputError(LlmError):
    """The model's reply broke the schema twice. Retrying the job will not help."""


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    mime_type: str = "image/png"


Part = str | ImagePart


@dataclass
class LlmUsage:
    purpose: str
    model: str
    prompt_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 1

    def as_detail(self) -> dict[str, object]:
        return {
            "purpose": self.purpose,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
        }


@dataclass
class LlmReply:
    text: str
    usage: LlmUsage


@dataclass
class Turn:
    """One message in a conversation: the model's earlier reply, or a user message."""

    role: str  # "user" or "model"
    parts: list[Part] = field(default_factory=list)


class LlmClient(Protocol):
    def generate(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        turns: list[Turn],
        schema: type[BaseModel] | None = None,
    ) -> LlmReply: ...


class GeminiClient:
    def __init__(
        self,
        api_key: SecretStr,
        *,
        max_concurrency: int = 2,
        timeout_s: float = 90,
        max_retries: int = 4,
        backoff_s: float = 2.0,
        sdk: genai.Client | None = None,
    ) -> None:
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        # The SDK's own retries are off; this class retries, so it can count and log them.
        self._sdk = sdk or genai.Client(
            api_key=api_key.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    @staticmethod
    def _content(turn: Turn) -> types.Content:
        parts = [
            types.Part.from_text(text=p)
            if isinstance(p, str)
            else types.Part.from_bytes(data=p.data, mime_type=p.mime_type)
            for p in turn.parts
        ]
        return types.Content(role=turn.role, parts=parts)

    def generate(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        turns: list[Turn],
        schema: type[BaseModel] | None = None,
    ) -> LlmReply:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json" if schema else "text/plain",
            response_schema=schema,
        )
        contents = [self._content(t) for t in turns]
        started = time.monotonic()
        for attempt in range(1, self._max_retries + 2):
            try:
                with self._semaphore:
                    response = self._sdk.models.generate_content(
                        model=model, contents=contents, config=config
                    )
            except genai_errors.APIError as exc:
                if exc.code not in RETRY_STATUS or attempt > self._max_retries:
                    logger.warning("llm %s failed: HTTP %s", purpose, exc.code)
                    raise LlmError(f"Gemini call failed with HTTP {exc.code}") from None
                reason = f"HTTP {exc.code}"
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt > self._max_retries:
                    logger.warning("llm %s failed: %s", purpose, type(exc).__name__)
                    raise LlmError("Gemini call failed: network error or timeout") from None
                reason = type(exc).__name__
            else:
                meta = response.usage_metadata
                usage = LlmUsage(
                    purpose=purpose,
                    model=model,
                    prompt_tokens=(meta.prompt_token_count or 0) if meta else 0,
                    output_tokens=(meta.candidates_token_count or 0) if meta else 0,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    attempts=attempt,
                )
                logger.info(
                    "llm call purpose=%s model=%s prompt_tokens=%d output_tokens=%d "
                    "latency_ms=%d attempts=%d",
                    usage.purpose,
                    usage.model,
                    usage.prompt_tokens,
                    usage.output_tokens,
                    usage.latency_ms,
                    usage.attempts,
                )
                return LlmReply(text=response.text or "", usage=usage)
            delay = self._backoff_s * 2 ** (attempt - 1) * (1 + random.random() / 4)  # noqa: S311
            logger.info("llm %s attempt %d: %s, retry in %.1fs", purpose, attempt, reason, delay)
            time.sleep(delay)
        raise AssertionError("unreachable")


def _error_summary(exc: Exception) -> str:
    """Describe a validation error without echoing the input (it holds document data)."""
    if isinstance(exc, ValidationError):
        problems = [
            f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        ]
        return "; ".join(problems[:10])
    return str(exc)[:300]


def generate_structured[M: BaseModel](
    client: LlmClient,
    schema: type[M],
    *,
    purpose: str,
    model: str,
    system: str,
    parts: list[Part],
    check: Callable[[M], None] | None = None,
) -> tuple[M, list[LlmUsage]]:
    """Call the model, validate the JSON reply, retry once with the error, then give up.

    `check` adds rules the schema cannot express (for example, page numbers that
    must fall inside the window). It raises ValueError to reject a reply.
    """
    turns = [Turn("user", list(parts))]
    usages: list[LlmUsage] = []
    for attempt in (1, 2):
        reply = client.generate(
            purpose=purpose, model=model, system=system, turns=turns, schema=schema
        )
        usages.append(reply.usage)
        try:
            parsed = schema.model_validate_json(reply.text)
            if check is not None:
                check(parsed)
            return parsed, usages
        except (ValidationError, ValueError) as exc:
            error = _error_summary(exc)
            logger.info("llm %s reply invalid (attempt %d)", purpose, attempt)
            turns += [Turn("model", [reply.text]), Turn("user", [prompts.retry_prompt(error)])]
    raise LlmOutputError(f"{purpose}: the model's reply did not match the schema twice")


def get_llm_client(settings: Settings) -> GeminiClient:
    if settings.gemini_api_key is None:
        raise RuntimeError("GEMINI_API_KEY must be set to run extraction")
    return GeminiClient(
        settings.gemini_api_key,
        max_concurrency=settings.llm_max_concurrency,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )


def require_model(name: str | None, setting: str) -> str:
    if not name:
        raise RuntimeError(f"{setting} must be set to run extraction")
    return name
