"""The common internal structure every reader returns.

PDFs and images become pages of text. Spreadsheets and CSV files become sheets
of rows. Later stages read these and never care which reader made them.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.db.enums import PageMethod, SourceKind


class FileKind(StrEnum):
    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    TIFF = "tiff"
    XLSX = "xlsx"
    XLS = "xls"
    CSV = "csv"

    @property
    def mime_type(self) -> str:
        return MIME_TYPES[self]

    @property
    def extension(self) -> str:
        return "jpg" if self is FileKind.JPEG else self.value

    @property
    def source_kind(self) -> SourceKind:
        return SOURCE_KINDS[self]

    @property
    def is_paged(self) -> bool:
        return self.source_kind in (SourceKind.PDF, SourceKind.IMAGE)


MIME_TYPES = {
    FileKind.PDF: "application/pdf",
    FileKind.JPEG: "image/jpeg",
    FileKind.PNG: "image/png",
    FileKind.TIFF: "image/tiff",
    FileKind.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileKind.XLS: "application/vnd.ms-excel",
    FileKind.CSV: "text/csv",
}
KIND_BY_MIME = {mime: kind for kind, mime in MIME_TYPES.items()}

SOURCE_KINDS = {
    FileKind.PDF: SourceKind.PDF,
    FileKind.JPEG: SourceKind.IMAGE,
    FileKind.PNG: SourceKind.IMAGE,
    FileKind.TIFF: SourceKind.IMAGE,
    FileKind.XLSX: SourceKind.SPREADSHEET,
    FileKind.XLS: SourceKind.SPREADSHEET,
    FileKind.CSV: SourceKind.CSV,
}


class PageContent(BaseModel):
    page_number: int = Field(ge=1)  # 1-based
    text: str
    method: PageMethod
    ocr_confidence: float | None = Field(default=None, ge=0, le=100)  # OCR pages only
    skew_degrees: float | None = None  # rotation that OCR cleanup removed


class SheetContent(BaseModel):
    sheet_index: int = Field(ge=0)
    sheet_name: str
    header_row: int | None = Field(default=None, ge=1)  # 1-based row in the source
    headers: list[str]
    rows: list[list[str | None]]  # every row has len(headers) cells
    row_numbers: list[int]  # 1-based source row of each entry in `rows`

    @property
    def row_count(self) -> int:
        return len(self.rows)


class Probe(BaseModel):
    """What detection learned before the full read."""

    kind: FileKind
    size_bytes: int
    page_count: int | None  # pages or frames; None for spreadsheets


class DocumentContent(BaseModel):
    kind: FileKind
    page_count: int | None
    pages: list[PageContent] = []
    sheets: list[SheetContent] = []
