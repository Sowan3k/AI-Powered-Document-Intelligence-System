"""Storage interface: local disk backend, Supabase backend over a fake transport."""

import json
import logging
import uuid
from pathlib import Path

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.storage import StorageError, StorageNotFoundError, get_storage, object_key
from app.storage.local import LocalStorage
from app.storage.supabase import SupabaseStorage, describe_key

# Fake key for tests only; the real value lives in Render's dashboard.
FAKE_KEY = "sb_secret_test-not-real"
DOC_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")
KEY = f"{DOC_ID}/original.pdf"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "in.pdf"
    path.write_bytes(b"%PDF-1.7 fake body " * 100)
    return path


def test_object_key_uses_the_document_id() -> None:
    assert object_key(DOC_ID, ".PDF") == KEY
    assert object_key(DOC_ID, "jpg").endswith("/original.jpg")


@pytest.mark.parametrize(
    "key", ["../etc/passwd", f"{DOC_ID}/../x", "invoice.pdf", f"/{KEY}", f"{DOC_ID}/a b.pdf"]
)
def test_bad_keys_are_refused(tmp_path: Path, source: Path, key: str) -> None:
    with pytest.raises(StorageError):
        LocalStorage(tmp_path).upload(key, source, "application/pdf")


def test_local_roundtrip(tmp_path: Path, source: Path) -> None:
    storage = LocalStorage(tmp_path / "store")
    storage.upload(KEY, source, "application/pdf")
    out = tmp_path / "out.pdf"
    storage.download(KEY, out)
    assert out.read_bytes() == source.read_bytes()
    storage.delete(KEY)
    storage.delete(KEY)  # deleting twice is fine
    with pytest.raises(StorageNotFoundError):
        storage.download(KEY, out)


# What hosted Supabase Storage answered on 5 Nov 2026 when the Authorization
# header was missing (Supabase storage log, POST /storage/v1/object/...).
MISSING_AUTHORIZATION = {
    "statusCode": "400",
    "code": "FST_ERR_VALIDATION",
    "error": "Bad Request",
    "message": "headers must have required property 'authorization'",
}


class FakeSupabase:
    """Records requests and answers like the hosted Storage API, header rules included.

    The first fake checked only paths and bodies, so it accepted requests that
    production refuses, and CI stayed green while every live upload failed (D32).
    It now enforces what the gateway and Storage enforce:

    - no `apikey` header: 401 from the gateway;
    - no `Authorization` header: 400 FST_ERR_VALIDATION from Storage;
    - a `Bearer sb_...` value must be the same key as `apikey`, which the gateway
      swaps for a service role token; anything else is refused.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []
        self.fail_next: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key_header = request.headers.get("apikey")
        if not key_header:
            return httpx.Response(401, json={"message": "No API key found in request"})
        authorization = request.headers.get("authorization")
        if authorization is None:
            return httpx.Response(400, json=MISSING_AUTHORIZATION)
        if authorization != f"Bearer {key_header}":
            return httpx.Response(
                403, json={"statusCode": "403", "error": "InvalidJWT", "message": "invalid"}
            )
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0), json={"error": "InternalError"})
        if request.method == "POST" and request.url.path == "/storage/v1/object/list/documents":
            limit = json.loads(request.read())["limit"]
            return httpx.Response(200, json=[{"name": k} for k in sorted(self.objects)][:limit])
        prefix = "/storage/v1/object/documents/"
        assert request.url.path.startswith(prefix)
        key = request.url.path[len(prefix) :]
        if request.method == "POST":
            self.objects[key] = request.read()
            return httpx.Response(200, json={"Key": f"documents/{key}"})
        if key not in self.objects:
            return httpx.Response(400, json={"statusCode": "404", "error": "not_found"})
        if request.method == "GET":
            return httpx.Response(200, content=self.objects[key])
        del self.objects[key]
        return httpx.Response(200, json={"message": "Successfully deleted"})


@pytest.fixture
def fake() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def supabase(fake: FakeSupabase) -> SupabaseStorage:
    return SupabaseStorage(
        "https://project.supabase.co/",
        SecretStr(FAKE_KEY),
        "documents",
        client=httpx.Client(transport=httpx.MockTransport(fake)),
        backoff_s=0,
    )


def test_supabase_roundtrip(supabase: SupabaseStorage, fake: FakeSupabase, source: Path) -> None:
    supabase.upload(KEY, source, "application/pdf")
    assert fake.objects[KEY] == source.read_bytes()
    out = source.with_name("out.pdf")
    supabase.download(KEY, out)
    assert out.read_bytes() == source.read_bytes()
    supabase.delete(KEY)
    assert KEY not in fake.objects


def test_secret_key_goes_in_apikey_and_authorization_headers(
    supabase: SupabaseStorage, fake: FakeSupabase, source: Path
) -> None:
    supabase.upload(KEY, source, "application/pdf")
    supabase.download(KEY, source.with_name("out.pdf"))
    supabase.delete(KEY)
    supabase.check()
    assert len(fake.requests) == 4
    for request in fake.requests:
        assert request.headers["apikey"] == FAKE_KEY
        # Hosted Storage needs Authorization; the gateway swaps "Bearer sb_..." (D32).
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    upload = fake.requests[0]
    assert upload.headers["content-type"] == "application/pdf"
    assert upload.headers["x-upsert"] == "true"
    assert upload.url == f"https://project.supabase.co/storage/v1/object/documents/{KEY}"


class ApikeyOnlyStorage(SupabaseStorage):
    """The header code that shipped before 5 Nov 2026 (D32, first version)."""

    def _headers(self) -> dict[str, str]:
        return {"apikey": self._key.get_secret_value()}


def test_the_fake_refuses_the_old_apikey_only_headers(
    fake: FakeSupabase, source: Path, caplog: pytest.LogCaptureFixture
) -> None:
    old = ApikeyOnlyStorage(
        "https://project.supabase.co/",
        SecretStr(FAKE_KEY),
        "documents",
        client=httpx.Client(transport=httpx.MockTransport(fake)),
        backoff_s=0,
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(StorageError) as info:
        old.upload(KEY, source, "application/pdf")
    # The same answer production gave, now with Storage's code in our message.
    assert str(info.value) == "storage upload failed with HTTP 400 (FST_ERR_VALIDATION)"
    assert len(fake.requests) == 1  # a 400 is not retried
    assert KEY not in fake.objects
    with pytest.raises(StorageError, match="FST_ERR_VALIDATION"):
        old.check()
    assert FAKE_KEY not in str(info.value)
    assert FAKE_KEY not in caplog.text


def test_check_lists_one_object(supabase: SupabaseStorage, fake: FakeSupabase) -> None:
    supabase.check()
    request = fake.requests[-1]
    assert request.method == "POST"
    assert request.url == "https://project.supabase.co/storage/v1/object/list/documents"
    assert json.loads(request.read()) == {"prefix": "", "limit": 1, "offset": 0}


def test_check_does_not_retry(supabase: SupabaseStorage, fake: FakeSupabase) -> None:
    fake.fail_next = [503]
    with pytest.raises(
        StorageError, match=r"^storage check failed with HTTP 503 \(InternalError\)$"
    ):
        supabase.check()
    assert len(fake.requests) == 1


def test_check_network_error() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to p.supabase.co")

    storage = SupabaseStorage(
        "https://p.supabase.co",
        SecretStr(FAKE_KEY),
        "documents",
        client=httpx.Client(transport=httpx.MockTransport(down)),
    )
    with pytest.raises(StorageError, match="^storage check failed: network error$"):
        storage.check()


@pytest.mark.parametrize(
    ("body", "suffix"),
    [
        ({"code": "FST_ERR_VALIDATION", "error": "Bad Request"}, " (FST_ERR_VALIDATION)"),
        ({"error": "InvalidJWT"}, " (InvalidJWT)"),
        ({"error": "a sentence with spaces, maybe holding data"}, ""),
        (["not", "a", "dict"], ""),
    ],
)
def test_only_a_storage_error_code_reaches_the_message(body: object, suffix: str) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=body)

    storage = SupabaseStorage(
        "https://p.supabase.co",
        SecretStr(FAKE_KEY),
        "documents",
        client=httpx.Client(transport=httpx.MockTransport(answer)),
    )
    with pytest.raises(StorageError) as info:
        storage.check()
    assert str(info.value) == "storage check failed with HTTP 400" + suffix


def test_local_check(tmp_path: Path) -> None:
    LocalStorage(tmp_path / "new" / "store").check()  # creates the folder
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")
    with pytest.raises(StorageError, match="cannot be created"):
        LocalStorage(blocker / "store").check()


def test_supabase_retries_server_errors(
    supabase: SupabaseStorage, fake: FakeSupabase, source: Path
) -> None:
    fake.fail_next = [503, 429]
    supabase.upload(KEY, source, "application/pdf")
    assert len(fake.requests) == 3
    assert fake.objects[KEY] == source.read_bytes()  # the retried body was complete


def test_supabase_gives_up_after_retries(
    supabase: SupabaseStorage, fake: FakeSupabase, source: Path
) -> None:
    fake.fail_next = [500, 500, 500]
    with pytest.raises(StorageError) as info:
        supabase.upload(KEY, source, "application/pdf")
    assert str(info.value) == "storage upload failed with HTTP 500 (InternalError)"
    assert FAKE_KEY not in str(info.value)


def test_supabase_does_not_retry_client_errors(
    supabase: SupabaseStorage, fake: FakeSupabase, source: Path
) -> None:
    fake.fail_next = [403]
    with pytest.raises(StorageError):
        supabase.upload(KEY, source, "application/pdf")
    assert len(fake.requests) == 1


def test_supabase_missing_object(supabase: SupabaseStorage, source: Path) -> None:
    with pytest.raises(StorageNotFoundError):
        supabase.download(KEY, source.with_name("out.pdf"))
    supabase.delete(KEY)  # a missing object is not an error on delete


def test_supabase_network_error(source: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    storage = SupabaseStorage(
        "https://p.supabase.co",
        SecretStr(FAKE_KEY),
        "documents",
        client=httpx.Client(transport=httpx.MockTransport(down)),
        backoff_s=0,
    )
    with pytest.raises(StorageError, match="network error"):
        storage.download(KEY, source.with_name("out.pdf"))


def test_factory_picks_backend(tmp_path: Path) -> None:
    local = get_storage(Settings(local_storage_dir=str(tmp_path)))
    assert isinstance(local, LocalStorage)
    remote = get_storage(
        Settings(
            storage_backend="supabase",
            supabase_url="https://p.supabase.co",
            supabase_service_role_key=FAKE_KEY,
        )
    )
    assert isinstance(remote, SupabaseStorage)


def test_production_defaults_to_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    settings = Settings()
    assert settings.resolved_storage_backend == "supabase"
    with pytest.raises(RuntimeError, match="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"):
        get_storage(settings)
    assert Settings(app_env="development").resolved_storage_backend == "local"


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        (FAKE_KEY, "an sb_secret key"),
        ("sb_publishable_abc", "an sb_publishable key"),
        ("eyJhbGciOi.eyJyb2xlIjoi.c2lnbmF0dXJl", "a legacy JWT key"),
        ("service_role", "in an unknown format"),
    ],
)
def test_describe_key_names_the_kind_never_the_key(value: str, kind: str) -> None:
    text = describe_key(SecretStr(value))
    assert text.startswith(kind)
    assert text.endswith(f"{len(value)} characters")
    assert value not in text


@pytest.mark.parametrize("pasted", [f" {FAKE_KEY}\n", f'"{FAKE_KEY}"', f"'{FAKE_KEY}' "])
def test_spaces_and_quotes_around_the_key_are_removed(
    pasted: str, fake: FakeSupabase, source: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        storage = SupabaseStorage(
            "https://project.supabase.co",
            SecretStr(pasted),
            "documents",
            client=httpx.Client(transport=httpx.MockTransport(fake)),
            backoff_s=0,
        )
    storage.upload(KEY, source, "application/pdf")  # the fake refuses anything but the clean key
    assert fake.requests[-1].headers["apikey"] == FAKE_KEY
    assert "spaces or quotes" in caplog.text
    assert "the Supabase key is an sb_secret key" in caplog.text
    assert FAKE_KEY not in caplog.text


def test_a_refused_check_logs_the_key_kind(caplog: pytest.LogCaptureFixture) -> None:
    def gateway(request: httpx.Request) -> httpx.Response:
        # Production on 5 Nov: the gateway did not recognise the key and passed it on.
        return httpx.Response(400, json={"statusCode": "403", "error": "AccessDenied"})

    storage = SupabaseStorage(
        "https://p.supabase.co",
        SecretStr("not-a-real-key"),
        "documents",
        client=httpx.Client(transport=httpx.MockTransport(gateway)),
    )
    with caplog.at_level(logging.WARNING), pytest.raises(StorageError, match="AccessDenied"):
        storage.check()
    assert "the key is in an unknown format" in caplog.text
    assert "not-a-real-key" not in caplog.text
