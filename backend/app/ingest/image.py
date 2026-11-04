"""Image reader for JPEG, PNG and multi-page TIFF. Every frame goes to OCR."""

import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from app.core.config import Settings
from app.db.enums import PageMethod
from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.limits import check_page_count
from app.ingest.ocr import ocr_image
from app.ingest.schemas import PageContent

# Refuse decompression bombs. 80 megapixels covers an A3 scan at 600 DPI.
Image.MAX_IMAGE_PIXELS = 80_000_000


@contextmanager
def open_image(path: Path) -> Iterator[Image.Image]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(path)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise IngestError(IngestErrorCode.TOO_LARGE, "the image has too many pixels") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the image cannot be opened") from None
    try:
        yield img
    finally:
        img.close()


def count_frames(path: Path, settings: Settings) -> int:
    with open_image(path) as img:
        count = getattr(img, "n_frames", 1)
    check_page_count(count, settings)
    return count


def _frame_to_gray(frame: Image.Image) -> np.ndarray:
    try:
        frame.load()
        frame = ImageOps.exif_transpose(frame)  # phone photos store rotation in EXIF
        return np.asarray(frame.convert("L"))
    except Image.DecompressionBombError:
        raise IngestError(IngestErrorCode.TOO_LARGE, "the image has too many pixels") from None
    except (OSError, ValueError, SyntaxError):
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the image data is damaged") from None


def iter_pages(path: Path, settings: Settings) -> Iterator[PageContent]:
    with open_image(path) as img:
        check_page_count(getattr(img, "n_frames", 1), settings)
        for number, frame in enumerate(ImageSequence.Iterator(img), start=1):
            gray = _frame_to_gray(frame)
            result = ocr_image(gray, settings.ocr_timeout_s)
            del gray
            yield PageContent(
                page_number=number,
                text=result.text,
                method=PageMethod.OCR,
                ocr_confidence=result.confidence,
                skew_degrees=result.skew_degrees,
            )
