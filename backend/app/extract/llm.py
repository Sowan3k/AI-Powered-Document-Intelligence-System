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


class CallRateLimiter:
    """Keeps calls under a per-minute quota (free tiers count requests per minute)."""

    def __init__(self, per_minute: int | None, window_s: float = 60.0) -> None:
        self.per_minute = per_minute
        self.window_s = window_s
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Wait for a free slot. Returns the seconds waited."""
        if not self.per_minute:
            return 0.0
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                self._calls = [t for t in self._calls if t > now - self.window_s]
                if len(self._calls) < self.per_minute:
                    self._calls.append(now)
                    return waited
                pause = self._calls[0] + self.window_s - now
            time.sleep(pause)
            waited += pause


def retry_delay(exc: genai_errors.APIError) -> float | None:
    """The server's own retryDelay hint on a 429, in seconds, if it sent one."""
    try:
        for item in exc.details["error"].get("details", []):  # type: ignore[index]
            delay = str(item.get("retryDelay", ""))
            if delay.endswith("s"):
                return float(delay[:-1])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return None


MAX_DELAY_S = 60.0
QUOTA_DELAY_S = 15.0  # a per-minute quota needs more than a few seconds to refill


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

    def embed(
        self, *, model: str, texts: list[str], dim: int
    ) -> tuple[list[list[float]], LlmUsage]:
        """One vector per text, each `dim` long."""
        ...


class GeminiClient:
    def __init__(
        self,
        api_key: SecretStr,
        *,
        max_concurrency: int = 2,
        timeout_s: float = 90,
        max_retries: int = 4,
        backoff_s: float = 2.0,
        calls_per_minute: int | None = None,
        quota_delay_s: float = QUOTA_DELAY_S,
        sdk: genai.Client | None = None,
    ) -> None:
        self._quota_delay_s = quota_delay_s
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._rate = CallRateLimiter(calls_per_minute)
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

    def _with_retries(self, purpose: str, call):  # type: ignore[no-untyped-def]
        """Run `call()` under the semaphore, retrying 408, 429, 5xx and timeouts."""
        for attempt in range(1, self._max_retries + 2):
            hint = None
            try:
                waited = self._rate.acquire()
                if waited:
                    logger.info("llm %s waited %.1fs for the per-minute quota", purpose, waited)
                with self._semaphore:
                    return call(), attempt
            except genai_errors.APIError as exc:
                if exc.code not in RETRY_STATUS or attempt > self._max_retries:
                    logger.warning("llm %s failed: HTTP %s", purpose, exc.code)
                    raise LlmError(f"Gemini call failed with HTTP {exc.code}") from None
                reason = f"HTTP {exc.code}"
                if exc.code == 429:
                    hint = max(retry_delay(exc) or 0.0, self._quota_delay_s)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt > self._max_retries:
                    logger.warning("llm %s failed: %s", purpose, type(exc).__name__)
                    raise LlmError("Gemini call failed: network error or timeout") from None
                reason = type(exc).__name__
            delay = self._backoff_s * 2 ** (attempt - 1) * (1 + random.random() / 4)  # noqa: S311
            if hint is not None:
                delay = min(max(delay, hint), MAX_DELAY_S)
            logger.info("llm %s attempt %d: %s, retry in %.1fs", purpose, attempt, reason, delay)
            time.sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _log(usage: LlmUsage) -> None:
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
        response, attempts = self._with_retries(
            purpose,
            lambda: self._sdk.models.generate_content(
                model=model, contents=contents, config=config
            ),
        )
        meta = response.usage_metadata
        usage = LlmUsage(
            purpose=purpose,
            model=model,
            prompt_tokens=(meta.prompt_token_count or 0) if meta else 0,
            output_tokens=(meta.candidates_token_count or 0) if meta else 0,
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=attempts,
        )
        self._log(usage)
        return LlmReply(text=response.text or "", usage=usage)

    def embed(
        self, *, model: str, texts: list[str], dim: int
    ) -> tuple[list[list[float]], LlmUsage]:
        config = types.EmbedContentConfig(output_dimensionality=dim)
        started = time.monotonic()
        response, attempts = self._with_retries(
            "embed",
            lambda: self._sdk.models.embed_content(model=model, contents=texts, config=config),
        )
        vectors = [list(e.values or []) for e in (response.embeddings or [])]
        if len(vectors) != len(texts) or any(len(v) != dim for v in vectors):
            raise LlmError(f"embedding reply had the wrong shape for {len(texts)} texts of {dim}")
        usage = LlmUsage(
            purpose="embed",
            model=model,
            prompt_tokens=sum(len(t) // 4 for t in texts),  # estimate; embed replies carry no count
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=attempts,
        )
        self._log(usage)
        return vectors, usage


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
        calls_per_minute=settings.llm_calls_per_minute,
    )


def require_model(name: str | None, setting: str) -> str:
    if not name:
        raise RuntimeError(f"{setting} must be set to run extraction")
    return name
