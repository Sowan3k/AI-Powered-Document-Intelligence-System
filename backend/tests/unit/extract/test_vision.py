"""Page images for the vision fallback."""

from pathlib import Path

import cv2
import numpy as np

from app.extract import vision
from app.ingest.schemas import FileKind
from tests.conftest import FakeLlmClient


def size_of(png: bytes) -> tuple[int, int]:
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
    return image.shape


def test_pdf_pages_render_only_the_wanted_ones(synthetic_dir: Path) -> None:
    images = list(
        vision.page_images(synthetic_dir / "multi_invoice.pdf", FileKind.PDF, {2, 4}, 100)
    )
    assert [n for n, _ in images] == [2, 4]
    assert all(png.startswith(b"\x89PNG") for _, png in images)


def test_tiff_frames(synthetic_dir: Path) -> None:
    images = list(
        vision.page_images(synthetic_dir / "scan_two_pages.tiff", FileKind.TIFF, {2}, 200)
    )
    assert [n for n, _ in images] == [2]


def test_large_pages_are_shrunk(synthetic_dir: Path) -> None:
    [(_, png)] = vision.page_images(synthetic_dir / "digital_classic_0.pdf", FileKind.PDF, {1}, 400)
    assert max(size_of(png)) <= vision.MAX_SIDE


def test_transcribe_sends_image_then_instruction() -> None:
    fake = FakeLlmClient(["  Invoice INV-1\nTotal 5.00  "])
    text, usage = vision.transcribe(fake, "vision-model", b"\x89PNGdata")
    assert text == "Invoice INV-1\nTotal 5.00"
    assert usage.purpose == "vision_transcribe"
    [call] = fake.calls
    assert call.schema is None and call.model == "vision-model"
    assert call.turns[0].parts[0].data == b"\x89PNGdata"
