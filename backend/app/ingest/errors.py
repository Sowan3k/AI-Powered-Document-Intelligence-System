"""Failure codes for ingestion. A failed file gets one of these and the batch goes on."""

from enum import StrEnum


class IngestErrorCode(StrEnum):
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    ENCRYPTED_FILE = "ENCRYPTED_FILE"  # password-protected workbook
    EMPTY_FILE = "EMPTY_FILE"
    TOO_LARGE = "TOO_LARGE"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    TOO_MANY_FILES = "TOO_MANY_FILES"


class IngestError(Exception):
    """A file cannot be ingested. The message is safe to show and to log."""

    def __init__(self, code: IngestErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"IngestError({self.code.value}, {self.message!r})"
