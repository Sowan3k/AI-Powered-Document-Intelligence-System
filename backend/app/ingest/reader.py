"""One entry point for every file type.

`probe` checks size, type and page limits before any heavy work. `iter_pages`
streams pages for PDFs and images. `read_sheets` returns spreadsheet tables.
`read_document` collects everything, for small files and tests.
"""

from collections.abc import Iterator
from pathlib import Path

from app.core.config import Settings
from app.ingest import image, pdf, spreadsheet
from app.ingest.detect import detect_kind
from app.ingest.limits import check_file_size
from app.ingest.schemas import DocumentContent, FileKind, PageContent, Probe, SheetContent

IMAGE_KINDS = (FileKind.JPEG, FileKind.PNG, FileKind.TIFF)


def probe(path: Path, settings: Settings) -> Probe:
    size = path.stat().st_size
    check_file_size(size, settings)
    kind = detect_kind(path, settings)
    if kind is FileKind.PDF:
        page_count: int | None = pdf.count_pages(path, settings)
    elif kind in IMAGE_KINDS:
        page_count = image.count_frames(path, settings)
    else:
        page_count = None
    return Probe(kind=kind, size_bytes=size, page_count=page_count)


def iter_pages(path: Path, kind: FileKind, settings: Settings) -> Iterator[PageContent]:
    if kind is FileKind.PDF:
        return pdf.iter_pages(path, settings)
    if kind in IMAGE_KINDS:
        return image.iter_pages(path, settings)
    raise ValueError(f"{kind} has no pages")


def read_sheets(path: Path, kind: FileKind) -> list[SheetContent]:
    if kind is FileKind.XLSX:
        return spreadsheet.read_xlsx(path)
    if kind is FileKind.XLS:
        return spreadsheet.read_xls(path)
    if kind is FileKind.CSV:
        return spreadsheet.read_csv(path)
    raise ValueError(f"{kind} has no sheets")


def read_document(path: Path, settings: Settings) -> DocumentContent:
    found = probe(path, settings)
    if found.kind.is_paged:
        return DocumentContent(
            kind=found.kind,
            page_count=found.page_count,
            pages=list(iter_pages(path, found.kind, settings)),
        )
    return DocumentContent(kind=found.kind, page_count=None, sheets=read_sheets(path, found.kind))
