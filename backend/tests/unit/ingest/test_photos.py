"""The phone photo set in the evaluation dataset (eval/generate/synth)."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.ingest.reader import read_document

pytestmark = pytest.mark.tesseract


@pytest.fixture(scope="module")
def with_photos(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[dict]]:
    from synth.dataset import build

    out = tmp_path_factory.mktemp("photos")
    return out, build(out, seed=7, scale=1, photos=3 * 3)


def test_photos_leave_every_other_file_unchanged(
    with_photos: tuple[Path, list[dict]], synthetic_dir: Path, manifest: list[dict]
) -> None:
    out, entries = with_photos
    assert entries[: len(manifest)] == manifest
    for entry in manifest:
        truth = synthetic_dir / f"{entry['file']}.json"
        if truth.exists():
            assert (out / truth.name).read_text() == truth.read_text()


def test_each_photo_is_a_one_page_jpeg_with_its_truth(
    with_photos: tuple[Path, list[dict]], manifest: list[dict]
) -> None:
    out, entries = with_photos
    photos = entries[len(manifest) :]
    assert len(photos) == 9
    levels = set()
    for entry in photos:
        truth = json.loads((out / f"{entry['file']}.json").read_text())
        assert truth["group"] == "photo"
        assert len(truth["invoices"]) == 1
        levels.add(truth["level"])
        doc = read_document(out / entry["file"], Settings())
        assert doc.kind.value == "jpeg"
        assert [p.method.value for p in doc.pages] == ["ocr"]
    assert levels == {"mild", "medium", "hard"}


def test_harder_photos_give_lower_ocr_confidence(
    with_photos: tuple[Path, list[dict]], manifest: list[dict]
) -> None:
    out, entries = with_photos
    confidence: dict[str, list[float]] = {"mild": [], "medium": [], "hard": []}
    for entry in entries[len(manifest) :]:
        level = json.loads((out / f"{entry['file']}.json").read_text())["level"]
        page = read_document(out / entry["file"], Settings()).pages[0]
        confidence[level].append(page.ocr_confidence or 0)
    mean = {k: sum(v) / len(v) for k, v in confidence.items()}
    assert mean["mild"] > mean["medium"] > mean["hard"]
    # Hard photos must reach the vision fallback (OCR_CONFIDENCE_THRESHOLD is 60).
    assert max(confidence["hard"]) < Settings().ocr_confidence_threshold
