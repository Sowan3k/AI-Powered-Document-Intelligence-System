"""Image reader for JPEG, PNG and multi-page TIFF. Every frame goes to OCR."""

import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import cv2
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
# A phone photo goes to the vision model anyway (D82), so its OCR is only the
# fallback. At full size (12 megapixels) Tesseract ran past its 120 s timeout on
# the free CPU, holding the photo for two minutes; 2,400 px is about 200 dpi for
# an A4 page, enough for Tesseract (D88).
PHOTO_OCR_SIDE = 2400


def _photo_size(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    if max(h, w) <= PHOTO_OCR_SIDE:
        return gray
    scale = PHOTO_OCR_SIDE / max(h, w)
    return cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


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
        photo = settings.vision_for_photos and img.format in ("JPEG", "PNG")
        for number, frame in enumerate(ImageSequence.Iterator(img), start=1):
            gray = _frame_to_gray(frame)
            if photo:
                gray = _photo_size(gray)
            result = ocr_image(gray, settings.ocr_timeout_s)
            del gray
            yield PageContent(
                page_number=number,
                text=result.text,
                method=PageMethod.OCR,
                ocr_confidence=result.confidence,
                skew_degrees=result.skew_degrees,
            )
