"""The storage interface and the object key rule."""

import re
import uuid
from pathlib import Path
from typing import Protocol

# Keys are always "<document uuid>/original.<ext>". User file names never reach storage.
KEY_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[a-z0-9._-]{1,40}$"
)


class StorageError(Exception):
    """A storage call failed. The message holds no secrets and no file content."""


class StorageNotFoundError(StorageError):
    """The object does not exist."""


def object_key(document_id: uuid.UUID, extension: str) -> str:
    """Build the storage key for a document's original file."""
    key = f"{document_id}/original.{extension.lower().lstrip('.')}"
    check_key(key)
    return key


def check_key(key: str) -> None:
    """Reject anything that is not a key built by `object_key` (no path tricks)."""
    if not KEY_PATTERN.fullmatch(key) or ".." in key:
        raise StorageError("invalid storage key")


class FileStorage(Protocol):
    def upload(self, key: str, source: Path, content_type: str) -> None:
        """Store the file at `source` under `key`. Overwrites an existing object."""
        ...

    def download(self, key: str, dest: Path) -> None:
        """Write the object to `dest`. Raises StorageNotFoundError if it is missing."""
        ...

    def delete(self, key: str) -> None:
        """Remove the object. Deleting a missing object is not an error."""
        ...
