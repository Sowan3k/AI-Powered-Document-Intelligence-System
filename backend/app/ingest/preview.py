"""One page of an uploaded file as a JPEG, for the reviewer to look at (D83).

The web app shows these images rather than the PDF itself. A PDF inside the
page needs the browser's PDF viewer, which most phone browsers lack and which
the app's content security policy blocks as a plugin. An image works everywhere.
"""

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps, ImageSequence

from app.ingest.schemas import FileKind

PREVIEW_KINDS = {FileKind.PDF, FileKind.TIFF, FileKind.JPEG, FileKind.PNG}
MAX_SIDE = 1800  # pixels: sharp on a phone, light enough to send
DPI = 150
QUALITY = 82


class PageNotFoundError(Exception):
    """The file has no page with that number."""


def page_jpeg(path: Path, kind: FileKind, number: int) -> bytes:
    """Page `number` (from 1) in colour, its longer side at most MAX_SIDE pixels."""
    if kind is FileKind.PDF:
        with pymupdf.open(path, filetype="pdf") as doc:
            if not 1 <= number <= doc.page_count:
                raise PageNotFoundError(number)
            page = doc.load_page(number - 1)
            # A huge page (a poster, a plan) is drawn smaller, never larger than MAX_SIDE.
            longest = max(page.rect.width, page.rect.height) / 72  # inches
            dpi = min(DPI, int(MAX_SIDE / longest)) if longest else DPI
            pix = page.get_pixmap(dpi=max(dpi, 1), colorspace=pymupdf.csRGB, alpha=False)
            return pix.tobytes(output="jpeg", jpg_quality=QUALITY)
    with Image.open(path) as img:
        for n, frame in enumerate(ImageSequence.Iterator(img), start=1):
            if n == number:
                picture = ImageOps.exif_transpose(frame).convert("RGB")
                picture.thumbnail((MAX_SIDE, MAX_SIDE))
                out = io.BytesIO()
                picture.save(out, format="JPEG", quality=QUALITY)
                return out.getvalue()
    raise PageNotFoundError(number)
