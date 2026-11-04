"""The Gemini client (with a fake SDK) and the schema-validated call."""

import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel, SecretStr

from app.core.config import Settings
from app.extract import prompts
from app.extract.llm import (
    GeminiClient,
    ImagePart,
    LlmError,
    LlmOutputError,
    Turn,
    generate_structured,
    get_llm_client,
)
from tests.conftest import FakeLlmClient


class Answer(BaseModel):
    total: str | None


def ok_response(text: str = '{"total": "5.00"}') -> SimpleNamespace:
    meta = SimpleNamespace(prompt_token_count=321, candidates_token_count=12)
    return SimpleNamespace(text=text, usage_metadata=meta)


class FakeModels:
    def __init__(self, outcomes: list) -> None:
        self.outcomes = outcomes
        self.calls: list[dict] = []
        self.in_flight = 0
        self.peak = 0
        self.lock = threading.Lock()

    def generate_content(self, **kwargs):  # type: ignore[no-untyped-def]
        with self.lock:
            self.calls.append(kwargs)
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            outcome = self.outcomes.pop(0) if self.outcomes else ok_response()
        time.sleep(0.01)
        with self.lock:
            self.in_flight -= 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client(outcomes: list, **kwargs) -> tuple[GeminiClient, FakeModels]:  # type: ignore[no-untyped-def]
    models = FakeModels(outcomes)
    sdk = SimpleNamespace(models=models)
    kwargs.setdefault("backoff_s", 0)
    kwargs.setdefault("quota_delay_s", 0)
    return GeminiClient(SecretStr("fake-key"), sdk=sdk, **kwargs), models  # type: ignore[arg-type]


def api_error(code: int) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": "x", "status": "X"}})


def call(c: GeminiClient, schema=Answer):  # type: ignore[no-untyped-def]
    return c.generate(
        purpose="test", model="m", system="sys", turns=[Turn("user", ["hi"])], schema=schema
    )


def test_returns_text_and_token_usage() -> None:
    c, models = client([ok_response()])
    reply = call(c)
    assert reply.text == '{"total": "5.00"}'
    assert (reply.usage.prompt_tokens, reply.usage.output_tokens, reply.usage.attempts) == (
        321,
        12,
        1,
    )
    config = models.calls[0]["config"]
    assert config.temperature == 0
    assert config.response_mime_type == "application/json"
    assert config.response_schema is Answer
    assert config.system_instruction == "sys"
    assert not getattr(config, "tools", None)  # the model gets no tools (AI rule 6)


@pytest.mark.parametrize("code", [429, 500, 503])
def test_retries_rate_limits_and_server_errors(code: int) -> None:
    c, models = client([api_error(code), api_error(code), ok_response()])
    assert call(c).usage.attempts == 3
    assert len(models.calls) == 3


def test_retries_timeouts() -> None:
    c, _ = client([httpx.ReadTimeout("slow"), ok_response()])
    assert call(c).usage.attempts == 2


def test_does_not_retry_client_errors() -> None:
    c, models = client([api_error(400)])
    with pytest.raises(LlmError, match="HTTP 400"):
        call(c)
    assert len(models.calls) == 1


def test_gives_up_after_max_retries() -> None:
    c, models = client([api_error(503)] * 5, max_retries=2)
    with pytest.raises(LlmError):
        call(c)
    assert len(models.calls) == 3


def test_semaphore_caps_calls_in_flight() -> None:
    c, models = client([], max_concurrency=2)
    threads = [threading.Thread(target=call, args=(c,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(models.calls) == 8
    assert models.peak <= 2


def test_images_are_sent_as_bytes() -> None:
    c, models = client([ok_response("page text")])
    c.generate(
        purpose="vision",
        model="v",
        system="s",
        turns=[Turn("user", [ImagePart(b"\x89PNG"), "Transcribe"])],
    )
    parts = models.calls[0]["contents"][0].parts
    assert parts[0].inline_data.data == b"\x89PNG"
    assert parts[1].text == "Transcribe"
    assert models.calls[0]["config"].response_mime_type == "text/plain"


def test_log_lines_hold_no_document_text(caplog: pytest.LogCaptureFixture) -> None:
    c, _ = client([ok_response('{"total": "SECRET-TOTAL"}')])
    caplog.set_level("INFO")
    c.generate(purpose="t", model="m", system="s", turns=[Turn("user", ["SECRET-INPUT"])])
    assert "prompt_tokens=321" in caplog.text
    assert "SECRET" not in caplog.text


def test_structured_valid_first_time() -> None:
    fake = FakeLlmClient([{"total": "5.00"}])
    answer, usages = generate_structured(
        fake, Answer, purpose="p", model="m", system="s", parts=["x"]
    )
    assert answer.total == "5.00" and len(usages) == 1


def test_structured_retries_once_with_the_error() -> None:
    fake = FakeLlmClient(['{"total": 5', {"total": "5.00"}])
    answer, usages = generate_structured(
        fake, Answer, purpose="p", model="m", system="s", parts=["DOC"]
    )
    assert answer.total == "5.00" and len(usages) == 2
    retry = fake.calls[1].turns
    assert [t.role for t in retry] == ["user", "model", "user"]
    assert "rejected" in retry[2].parts[0]


def test_structured_fails_after_two_bad_replies() -> None:
    fake = FakeLlmClient(["not json", '{"total": ["list"]}'])
    with pytest.raises(LlmOutputError):
        generate_structured(fake, Answer, purpose="p", model="m", system="s", parts=["x"])
    assert len(fake.calls) == 2


def test_retry_message_does_not_echo_document_values() -> None:
    fake = FakeLlmClient([{"total": ["CONFIDENTIAL-VALUE"]}, {"total": "1"}])
    generate_structured(fake, Answer, purpose="p", model="m", system="s", parts=["x"])
    message = fake.calls[1].turns[2].parts[0]
    assert "total" in message
    assert "CONFIDENTIAL-VALUE" not in message


def test_check_hook_rejects_and_retries() -> None:
    fake = FakeLlmClient([{"total": "bad"}, {"total": "5.00"}])

    def check(answer: Answer) -> None:
        if answer.total == "bad":
            raise ValueError("total: must be printed on the page")

    answer, _ = generate_structured(
        fake, Answer, purpose="p", model="m", system="s", parts=["x"], check=check
    )
    assert answer.total == "5.00"
    assert "must be printed" in fake.calls[1].turns[2].parts[0]


def test_retry_prompt_is_in_prompts_module() -> None:
    assert "rejected" in prompts.retry_prompt("x")


def test_factory_needs_a_key() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        get_llm_client(Settings(gemini_api_key=None))
    assert isinstance(get_llm_client(Settings(gemini_api_key="fake-key")), GeminiClient)


def test_fake_reply_is_json() -> None:
    fake = FakeLlmClient([Answer(total="1")])
    reply = fake.generate(purpose="p", model="m", system="s", turns=[])
    assert json.loads(reply.text) == {"total": "1"}


def test_rate_limiter_spaces_calls() -> None:
    from app.extract.llm import CallRateLimiter

    limiter = CallRateLimiter(per_minute=2, window_s=0.3)
    started = time.monotonic()
    waits = [limiter.acquire() for _ in range(4)]
    assert waits[:2] == [0.0, 0.0]
    assert waits[2] > 0 and time.monotonic() - started >= 0.3


def test_rate_limiter_off() -> None:
    from app.extract.llm import CallRateLimiter

    assert CallRateLimiter(None).acquire() == 0.0


def test_quota_error_waits_as_the_server_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.extract import llm as llm_module

    slept: list[float] = []
    monkeypatch.setattr(llm_module.time, "sleep", slept.append)
    quota = genai_errors.APIError(
        429,
        {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"}]}},
    )  # fmt: skip
    c, models = client([quota, api_error(429), ok_response()], backoff_s=1, quota_delay_s=15)
    assert call(c).usage.attempts == 3
    waits = [x for x in slept if x >= 1]  # the fake SDK itself sleeps 0.01 s per call
    assert waits == [21.0, 15.0]  # the server's hint, then at least the quota delay
    assert llm_module.retry_delay(api_error(500)) is None
