"""File storage behind one small interface (DECISIONS.md D32).

Production stores files in the private Supabase Storage bucket. docker-compose
and tests store them on local disk. Callers only see `FileStorage`.
"""

from app.storage.base import FileStorage, StorageError, StorageNotFoundError, object_key
from app.storage.factory import get_storage

__all__ = ["FileStorage", "StorageError", "StorageNotFoundError", "get_storage", "object_key"]
