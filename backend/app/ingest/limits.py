"""Upload and processing limits from settings."""

from app.core.config import Settings
from app.ingest.errors import IngestError, IngestErrorCode

MB = 1024 * 1024


def check_batch(file_count: int, settings: Settings) -> None:
    if file_count > settings.max_files_per_batch:
        raise IngestError(
            IngestErrorCode.TOO_MANY_FILES,
            f"{file_count} files sent; the limit is {settings.max_files_per_batch} per batch",
        )


def check_file_size(size_bytes: int, settings: Settings) -> None:
    if size_bytes == 0:
        raise IngestError(IngestErrorCode.EMPTY_FILE, "the file is empty")
    if size_bytes > settings.max_file_mb * MB:
        raise IngestError(
            IngestErrorCode.TOO_LARGE, f"the file is larger than {settings.max_file_mb} MB"
        )


def check_page_count(page_count: int, settings: Settings) -> None:
    if page_count > settings.max_pdf_pages:
        raise IngestError(
            IngestErrorCode.TOO_MANY_PAGES,
            f"the file has {page_count} pages; the limit is {settings.max_pdf_pages}",
        )
