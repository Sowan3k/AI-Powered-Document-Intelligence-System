"""PDF reader: digital text with PyMuPDF, OCR for scanned pages.

Pages are read in batches of PDF_PAGE_BATCH_SIZE. Only one rendered page image
exists at a time, and PyMuPDF's cache is trimmed after each batch, so memory
stays flat on a 1,000-page file (CLAUDE.md coding rule 4).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pymupdf

from app.core.config import Settings
from app.db.enums import PageMethod
from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.limits import check_page_count
from app.ingest.ocr import ocr_image
from app.ingest.schemas import PageContent

logger = logging.getLogger(__name__)

# MuPDF prints repair notices to stderr; read them through mupdf_warnings() instead.
pymupdf.TOOLS.mupdf_display_errors(False)
# Signs that a page of a repaired file lost content: the file is damaged, not just untidy.
DAMAGE_SIGNS = ("format error", "cannot load", "non-page object", "syntax error")


@contextmanager
def open_pdf(path: Path) -> Iterator[pymupdf.Document]:
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception:
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the PDF cannot be opened") from None
    try:
        if doc.needs_pass:
            raise IngestError(IngestErrorCode.ENCRYPTED_PDF, "the PDF is password protected")
        if doc.page_count == 0:
            raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the PDF has no readable pages")
        yield doc
    finally:
        doc.close()


def count_pages(path: Path, settings: Settings) -> int:
    with open_pdf(path) as doc:
        count = doc.page_count
    check_page_count(count, settings)
    return count


def is_scanned(text: str, min_chars: int) -> bool:
    """A page with almost no letters or digits is an image of text."""
    return sum(ch.isalnum() for ch in text) < min_chars


def render_gray(page: pymupdf.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    return image[:, : pix.width].copy()


def iter_pages(path: Path, settings: Settings) -> Iterator[PageContent]:
    with open_pdf(path) as doc:
        total = doc.page_count
        check_page_count(total, settings)
        batch = settings.pdf_page_batch_size
        for start in range(0, total, batch):
            for index in range(start, min(start + batch, total)):
                yield _read_page(doc, index, settings)
            pymupdf.TOOLS.store_shrink(100)  # drop cached page data before the next batch


def _read_page(doc: pymupdf.Document, index: int, settings: Settings) -> PageContent:
    pymupdf.TOOLS.mupdf_warnings(reset=True)
    try:
        page = doc.load_page(index)
        text = page.get_text("text", sort=True)
    except Exception:
        raise IngestError(
            IngestErrorCode.CORRUPTED_FILE, f"page {index + 1} of the PDF cannot be read"
        ) from None
    if doc.is_repaired:
        # MuPDF rebuilt a broken file. Many such files are fine, but a page that
        # reports missing content means the file was cut short or damaged.
        warnings = pymupdf.TOOLS.mupdf_warnings(reset=True).lower()
        if any(sign in warnings for sign in DAMAGE_SIGNS):
            raise IngestError(
                IngestErrorCode.CORRUPTED_FILE,
                f"the PDF is damaged: page {index + 1} has missing or broken content",
            )
    if not is_scanned(text, settings.scanned_page_min_chars):
        return PageContent(page_number=index + 1, text=text.strip(), method=PageMethod.DIGITAL)
    image = render_gray(page, settings.ocr_dpi)
    result = ocr_image(image, settings.ocr_timeout_s)
    del image
    # A scanned page's decoded image stays in MuPDF's cache; drop it now, not at the
    # end of the batch, so memory stays flat on a 512 MB instance.
    pymupdf.TOOLS.store_shrink(100)
    return PageContent(
        page_number=index + 1,
        text=result.text,
        method=PageMethod.OCR,
        ocr_confidence=result.confidence,
        skew_degrees=result.skew_degrees,
    )
