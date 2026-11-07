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
    assert all(img.startswith(b"\xff\xd8\xff") for _, img in images)  # JPEG (D86)


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


def test_second_model_takes_over_when_the_first_is_down() -> None:
    from app.extract.llm import LlmError
    from tests.conftest import FakeCall

    def reply(call: FakeCall) -> str:
        if call.model == "vision-model":
            raise LlmError("Gemini call failed with HTTP 503")
        return "Invoice INV-1"

    result = vision.transcribe_with_fallback(
        FakeLlmClient(reply), ["vision-model", "text-model"], b"png"
    )
    assert (result.text, result.model) == ("Invoice INV-1", "text-model")
    assert result.errors == ["vision-model: Gemini call failed with HTTP 503"]


def test_all_models_down_gives_no_text() -> None:
    from app.extract.llm import LlmError
    from tests.conftest import FakeCall

    def down(call: FakeCall) -> str:
        raise LlmError("Gemini call failed with HTTP 503")

    fake = FakeLlmClient(down)
    result = vision.transcribe_with_fallback(fake, ["v", "t", "v", None], b"png")
    assert result.text is None and len(result.errors) == 2
    assert [c.model for c in fake.calls] == ["v", "t"]  # each model tried once


def test_a_vision_model_that_just_failed_is_skipped_on_the_next_page() -> None:
    from app.extract.llm import LlmError
    from tests.conftest import FakeCall

    def reply(call: FakeCall) -> str:
        if call.model == "vision-model":
            raise LlmError("Gemini call failed with HTTP 503")
        return "Invoice INV-1"

    fake = FakeLlmClient(reply)
    for _ in range(2):
        result = vision.transcribe_with_fallback(fake, ["vision-model", "text-model"], b"png")
        assert result.model == "text-model"
    # The second page did not wait for the overloaded model again (D67).
    assert [c.model for c in fake.calls] == ["vision-model", "text-model", "text-model"]
    assert "skipped" in result.errors[0]


def test_a_page_read_upside_down_is_sent_the_right_way_up(synthetic_dir: Path) -> None:
    """Tesseract flipped it (D64), so the vision model gets it flipped too (D82)."""
    path = synthetic_dir / "scan_clean.png"
    [(_, plain)] = vision.page_images(path, FileKind.PNG, {1}, 200)
    [(_, turned)] = vision.page_images(path, FileKind.PNG, {1}, 200, turned=frozenset({1}))
    a = cv2.imdecode(np.frombuffer(plain, np.uint8), cv2.IMREAD_GRAYSCALE)
    b = cv2.imdecode(np.frombuffer(turned, np.uint8), cv2.IMREAD_GRAYSCALE)
    # JPEG is lossy, so the turned page matches within a few grey levels.
    diff = np.abs(b.astype(int) - np.rot90(a, 2).astype(int))
    assert b.shape == a.shape and diff.mean() < 3
