"""The image reader sizes phone photos for OCR (D88)."""

from pathlib import Path

import pytest

from app.core.config import Settings


def test_a_big_phone_photo_is_read_at_a_size_tesseract_can_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 12 megapixels Tesseract ran past its timeout on the free CPU (D88)."""
    from PIL import Image as PILImage

    from app.ingest import image as image_reader
    from app.ingest.ocr import OcrResult

    big = tmp_path / "photo.jpg"
    PILImage.new("L", (4000, 3000), 255).save(big, "JPEG")
    seen: list[tuple[int, int]] = []

    def fake_ocr(gray, timeout_s):  # type: ignore[no-untyped-def]
        seen.append(gray.shape)
        return OcrResult(text="", confidence=None, skew_degrees=0.0)

    monkeypatch.setattr(image_reader, "ocr_image", fake_ocr)
    list(image_reader.iter_pages(big, Settings()))
    assert seen == [(1800, 2400)]
    # Without the vision path, the photo keeps its full size for OCR.
    list(image_reader.iter_pages(big, Settings(vision_for_photos=False)))
    assert seen[-1] == (3000, 4000)
