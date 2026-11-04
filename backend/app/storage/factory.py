"""Pick the storage backend from settings."""

from pathlib import Path

from app.core.config import Settings, get_settings
from app.storage.base import FileStorage
from app.storage.local import LocalStorage
from app.storage.supabase import SupabaseStorage


def get_storage(settings: Settings | None = None) -> FileStorage:
    settings = settings or get_settings()
    if settings.resolved_storage_backend == "local":
        return LocalStorage(Path(settings.local_storage_dir))
    if not settings.supabase_url or settings.supabase_service_role_key is None:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set when STORAGE_BACKEND=supabase"
        )
    return SupabaseStorage(
        settings.supabase_url,
        settings.supabase_service_role_key,
        settings.supabase_bucket,
        timeout_s=settings.storage_timeout_s,
    )
