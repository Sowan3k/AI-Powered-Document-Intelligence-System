"""Supabase Storage over its REST API (no Supabase client library, see D17).

The key is a new-style secret key (`sb_secret_...`). Every call sends it in two
headers: `apikey` and `Authorization: Bearer`. Hosted Storage refuses a request
without an `Authorization` header (HTTP 400, FST_ERR_VALIDATION), and the API
gateway swaps a `Bearer sb_...` value for a service role token before the
request reaches Storage. Supabase's own clients send the same pair (D32).
The key never appears in logs or error messages.
"""

import logging
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2 as httpx
from pydantic import SecretStr

from app.storage.base import StorageError, StorageNotFoundError, check_key

logger = logging.getLogger(__name__)

CHUNK = 1024 * 1024
RETRIES = 3
CHECK_TIMEOUT_S = 5.0
# Storage error codes such as FST_ERR_VALIDATION or InvalidJWT. Only a value of
# this shape is copied into an error message; anything else in the body is not.
ERROR_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,39}$")


class SupabaseStorage:
    def __init__(
        self,
        base_url: str,
        secret_key: SecretStr,
        bucket: str,
        *,
        timeout_s: float = 60,
        client: httpx.Client | None = None,
        backoff_s: float = 1.0,
    ) -> None:
        self._root = f"{base_url.rstrip('/')}/storage/v1/object"
        self._base = f"{self._root}/{bucket}"
        self._bucket = bucket
        self._key = _clean_key(secret_key)
        self._backoff_s = backoff_s
        self._client = client or httpx.Client(timeout=timeout_s)

    def _headers(self) -> dict[str, str]:
        key = self._key.get_secret_value()
        return {"apikey": key, "Authorization": f"Bearer {key}"}

    def _call(self, op: str, send: Callable[[], httpx.Response]) -> httpx.Response:
        """Run one request with retries on network errors, 429 and 5xx."""
        for attempt in range(1, RETRIES + 1):
            try:
                response = send()
            except httpx.TransportError as exc:
                logger.warning("storage %s attempt %d: %s", op, attempt, type(exc).__name__)
                if attempt == RETRIES:
                    raise StorageError(f"storage {op} failed: network error") from None
            else:
                if response.status_code < 400:
                    return response
                retryable = response.status_code == 429 or response.status_code >= 500
                if not retryable or attempt == RETRIES:
                    return response
                logger.warning("storage %s attempt %d: HTTP %d", op, attempt, response.status_code)
            time.sleep(self._backoff_s * 2 ** (attempt - 1))
        raise AssertionError("unreachable")

    @staticmethod
    def _fail(op: str, response: httpx.Response) -> StorageError:
        # Storage reports a missing object as 404, or as 400 with "not_found" in the body.
        if response.status_code == 404 or (
            response.status_code == 400 and "not_found" in response.text.lower()
        ):
            return StorageNotFoundError("object not found")
        status = response.status_code
        return StorageError(f"storage {op} failed with HTTP {status}" + _code(response))

    def check(self) -> None:
        """List at most one object: proves the URL, the key and the bucket, without retries."""
        try:
            response = self._client.post(
                f"{self._root}/list/{self._bucket}",
                json={"prefix": "", "limit": 1, "offset": 0},
                headers=self._headers(),
                timeout=CHECK_TIMEOUT_S,
            )
        except httpx.TransportError:
            raise StorageError("storage check failed: network error") from None
        if response.status_code >= 400:
            status = response.status_code
            if status in (400, 401, 403):
                # The gateway only swaps keys it recognises; say which kind ours is.
                logger.warning("storage check refused; the key is %s", describe_key(self._key))
            raise StorageError(f"storage check failed with HTTP {status}" + _code(response))

    def upload(self, key: str, source: Path, content_type: str) -> None:
        check_key(key)
        size = source.stat().st_size

        def chunks() -> Iterator[bytes]:
            with source.open("rb") as fh:
                while block := fh.read(CHUNK):
                    yield block

        headers = {
            **self._headers(),
            "Content-Type": content_type,
            "Content-Length": str(size),
            # Keys are fresh UUIDs, so overwriting is safe and makes a retry harmless.
            "x-upsert": "true",
        }
        response = self._call(
            "upload",
            lambda: self._client.post(f"{self._base}/{key}", content=chunks(), headers=headers),
        )
        if response.status_code >= 400:
            raise self._fail("upload", response)

    def download(self, key: str, dest: Path) -> None:
        check_key(key)
        for attempt in range(1, RETRIES + 1):
            try:
                with self._client.stream(
                    "GET", f"{self._base}/{key}", headers=self._headers()
                ) as r:
                    if r.status_code >= 400:
                        r.read()
                        retryable = r.status_code == 429 or r.status_code >= 500
                        if not retryable or attempt == RETRIES:
                            raise self._fail("download", r)
                    else:
                        with dest.open("wb") as fh:
                            for block in r.iter_bytes(CHUNK):
                                fh.write(block)
                        return
            except httpx.TransportError as exc:
                logger.warning("storage download attempt %d: %s", attempt, type(exc).__name__)
                if attempt == RETRIES:
                    raise StorageError("storage download failed: network error") from None
            time.sleep(self._backoff_s * 2 ** (attempt - 1))

    def delete(self, key: str) -> None:
        check_key(key)
        response = self._call(
            "delete", lambda: self._client.delete(f"{self._base}/{key}", headers=self._headers())
        )
        if response.status_code >= 400:
            error = self._fail("delete", response)
            if not isinstance(error, StorageNotFoundError):
                raise error


def _code(response: httpx.Response) -> str:
    """Storage's error code in brackets, such as " (FST_ERR_VALIDATION)", or nothing."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    for field in ("code", "error"):
        value = body.get(field)
        if isinstance(value, str) and ERROR_CODE.fullmatch(value):
            return f" ({value})"
    return ""


def describe_key(key: SecretStr) -> str:
    """What kind of key this is, for logs: never the key, nor any part of it."""
    value = key.get_secret_value()
    if value.startswith("sb_secret_"):
        kind = "an sb_secret key"
    elif value.startswith("sb_publishable_"):
        kind = "an sb_publishable key, which cannot write to a private bucket"
    elif value.startswith("eyJ") and value.count(".") == 2:
        kind = "a legacy JWT key"
    else:
        kind = "in an unknown format (expected it to start with sb_secret_)"
    return f"{kind}, {len(value)} characters"


def _clean_key(key: SecretStr) -> SecretStr:
    """Drop spaces and one pair of quotes pasted around the key in a dashboard."""
    raw = key.get_secret_value()
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    if value != raw:
        logger.warning("storage key had spaces or quotes around it; they were removed")
    cleaned = SecretStr(value)
    logger.info("storage: the Supabase key is %s", describe_key(cleaned))
    return cleaned
