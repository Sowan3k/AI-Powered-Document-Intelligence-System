"""Allowed values for status-like columns.

The database stores these as VARCHAR with a CHECK constraint, not as native
PostgreSQL enums (see DECISIONS.md D19). Adding a value means editing the
enum here and writing a migration that replaces the CHECK constraint.
"""

from enum import StrEnum


class SourceKind(StrEnum):
    PDF = "pdf"
    IMAGE = "image"
    SPREADSHEET = "spreadsheet"
    CSV = "csv"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PageMethod(StrEnum):
    DIGITAL = "digital"
    OCR = "ocr"
    VISION = "vision"


class ReviewStatus(StrEnum):
    PENDING = "pending"  # extracted, not yet validated
    OK = "ok"  # validated, no error-level issues
    NEEDS_REVIEW = "needs_review"  # at least one error-level issue
    REVIEWED = "reviewed"  # a person checked it


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
