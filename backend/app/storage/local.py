"""Local disk storage for docker-compose and tests."""

import os
import shutil
import tempfile
from pathlib import Path

from app.storage.base import StorageError, StorageNotFoundError, check_key


class LocalStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        check_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("invalid storage key")
        return path

    def upload(self, key: str, source: Path, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file first, so a crash never leaves half a file.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        os.close(fd)
        try:
            shutil.copyfile(source, tmp)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def download(self, key: str, dest: Path) -> None:
        path = self._path(key)
        if not path.is_file():
            raise StorageNotFoundError("object not found")
        shutil.copyfile(path, dest)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def check(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise StorageError("storage check failed: folder cannot be created") from None
        if not os.access(self.root, os.W_OK):
            raise StorageError("storage check failed: folder is not writable")
