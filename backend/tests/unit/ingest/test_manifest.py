"""Phase 1 exit test: every fixture gives the expected structure or failure code."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.ingest.errors import IngestError
from app.ingest.reader import read_document

pytestmark = pytest.mark.tesseract


def _check(path: Path, expect: dict, settings: Settings) -> str | None:
    """Return a description of the mismatch, or None if the file behaves as expected."""
    try:
        doc = read_document(path, settings)
    except IngestError as exc:
        if expect.get("error") == exc.code.value:
            return None
        return f"failed with {exc.code.value}, expected {expect}"
    if "error" in expect:
        return f"read as {doc.kind.value}, expected {expect['error']}"
    if doc.kind.value != expect["kind"]:
        return f"kind {doc.kind.value}, expected {expect['kind']}"
    if "pages" in expect:
        if doc.page_count != expect["pages"] or len(doc.pages) != expect["pages"]:
            return f"{len(doc.pages)} pages, expected {expect['pages']}"
        if [p.page_number for p in doc.pages] != list(range(1, expect["pages"] + 1)):
            return "page numbers out of order"
        if {p.method.value for p in doc.pages} != set(expect["methods"]):
            return f"methods {[p.method.value for p in doc.pages]}, expected {expect['methods']}"
        floor = expect.get("min_confidence")
        if floor is not None and min(p.ocr_confidence or 0 for p in doc.pages) < floor:
            return f"OCR confidence {[p.ocr_confidence for p in doc.pages]} below {floor}"
        text = "\n".join(p.text for p in doc.pages)
    else:
        got = [(s.sheet_name, s.row_count, s.header_row) for s in doc.sheets]
        want = [(s["name"], s["rows"], s["header_row"]) for s in expect["sheets"]]
        if got != want:
            return f"sheets {got}, expected {want}"
        text = "\n".join(str(v) for s in doc.sheets for row in s.rows for v in row)
    missing = [n for n in expect.get("contains", []) if n not in text]
    return f"text lacks {missing}" if missing else None


def test_every_fixture_matches_the_manifest(synthetic_dir: Path, manifest: list[dict]) -> None:
    settings = Settings()
    problems = {}
    for entry in manifest:
        problem = _check(synthetic_dir / entry["file"], entry["expect"], settings)
        if problem:
            problems[entry["file"]] = problem
    assert problems == {}
    assert len(manifest) >= 25
