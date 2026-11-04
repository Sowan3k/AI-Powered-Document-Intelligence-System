"""Storage interface: local disk backend, Supabase backend over a fake transport."""

import uuid
from pathlib import Path

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.storage import StorageError, StorageNotFoundError, get_storage, object_key
from app.storage.local import LocalStorage
from app.storage.supabase import SupabaseStorage

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


class FakeSupabase:
    """Records requests and answers like the Storage API."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []
        self.fail_next: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0), json={"error": "busy"})
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


def test_secret_key_goes_only_in_apikey_header(
    supabase: SupabaseStorage, fake: FakeSupabase, source: Path
) -> None:
    supabase.upload(KEY, source, "application/pdf")
    supabase.download(KEY, source.with_name("out.pdf"))
    supabase.delete(KEY)
    for request in fake.requests:
        assert request.headers["apikey"] == FAKE_KEY
        # An sb_secret_ key is not a JWT; Supabase rejects it as a Bearer token.
        assert "authorization" not in request.headers
    upload = fake.requests[0]
    assert upload.headers["content-type"] == "application/pdf"
    assert upload.headers["x-upsert"] == "true"
    assert upload.url == f"https://project.supabase.co/storage/v1/object/documents/{KEY}"


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
    assert str(info.value) == "storage upload failed with HTTP 500"
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
