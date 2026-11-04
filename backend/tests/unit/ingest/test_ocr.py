"""Image cleanup and OCR."""

from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest

from app.core.config import Settings
from app.db.enums import PageMethod
from app.ingest import image, ocr
from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.pdf import render_gray


@pytest.fixture(scope="module")
def page_image(synthetic_dir: Path) -> np.ndarray:
    with pymupdf.open(synthetic_dir / "digital_classic_0.pdf") as doc:
        return render_gray(doc[0], 150)


@pytest.mark.parametrize("angle", [-4.0, -1.5, 0.0, 2.0, 5.0])
def test_estimate_skew_finds_the_tilt(page_image: np.ndarray, angle: float) -> None:
    tilted = ocr.rotate(page_image, -angle)  # tilt the page; cleanup must undo it
    assert ocr.estimate_skew(tilted) == pytest.approx(angle, abs=0.3)


def test_deskew_straightens(page_image: np.ndarray) -> None:
    tilted = ocr.rotate(page_image, 3.0)
    straight = ocr.rotate(tilted, ocr.estimate_skew(tilted))
    assert abs(ocr.estimate_skew(straight)) <= 0.3


def test_blank_image_has_no_skew() -> None:
    assert ocr.estimate_skew(np.full((300, 200), 255, np.uint8)) == 0.0


def test_clean_image_is_binary_and_upscaled() -> None:
    small = np.full((400, 500, 3), 200, np.uint8)  # upscaled at most 4x
    cv2.putText(small, "TOTAL 42.00", (10, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    binary, _ = ocr.clean_image(small)
    assert binary.ndim == 2
    assert binary.shape[1] >= ocr.MIN_WIDTH
    assert set(np.unique(binary)) <= {0, 255}


@pytest.mark.tesseract
def test_clean_scan_reads_well_and_noisy_scan_reports_low_confidence(
    synthetic_dir: Path,
) -> None:
    clean = list(image.iter_pages(synthetic_dir / "scan_clean.png", Settings()))
    noisy = list(image.iter_pages(synthetic_dir / "scan_heavy.jpg", Settings()))
    assert clean[0].method is PageMethod.OCR
    assert clean[0].ocr_confidence > 80
    assert noisy[0].ocr_confidence < clean[0].ocr_confidence


@pytest.mark.tesseract
def test_multi_page_tiff(synthetic_dir: Path) -> None:
    pages = list(image.iter_pages(synthetic_dir / "scan_two_pages.tiff", Settings()))
    assert [p.page_number for p in pages] == [1, 2]
    assert all(p.text for p in pages)


@pytest.mark.tesseract
def test_blank_image_gives_empty_text_and_zero_confidence() -> None:
    result = ocr.ocr_image(np.full((800, 1700), 255, np.uint8))
    assert result.text == "" and result.confidence == 0.0


def test_tesseract_timeout_gives_empty_page(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(ocr.pytesseract, "image_to_data", slow)
    assert ocr.run_tesseract(np.zeros((10, 10), np.uint8), 1) == ("", 0.0)


def test_truncated_image(synthetic_dir: Path) -> None:
    with pytest.raises(IngestError) as info:
        list(image.iter_pages(synthetic_dir / "truncated.png", Settings()))
    assert info.value.code is IngestErrorCode.CORRUPTED_FILE


def test_decompression_bomb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "big.png"
    cv2.imwrite(str(path), np.full((1000, 1000), 255, np.uint8))
    monkeypatch.setattr(image.Image, "MAX_IMAGE_PIXELS", 10_000)
    with pytest.raises(IngestError) as info:
        image.count_frames(path, Settings())
    assert info.value.code is IngestErrorCode.TOO_LARGE
