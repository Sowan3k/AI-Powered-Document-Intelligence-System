"""Upload limits from config: file size, files per batch, pages per document."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.ingest import reader
from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.limits import MB, check_batch, check_file_size


def test_batch_limit() -> None:
    settings = Settings(max_files_per_batch=3)
    check_batch(3, settings)
    with pytest.raises(IngestError) as info:
        check_batch(4, settings)
    assert info.value.code is IngestErrorCode.TOO_MANY_FILES


def test_file_size_limit() -> None:
    settings = Settings(max_file_mb=2)
    check_file_size(2 * MB, settings)
    with pytest.raises(IngestError) as info:
        check_file_size(2 * MB + 1, settings)
    assert info.value.code is IngestErrorCode.TOO_LARGE
    with pytest.raises(IngestError) as info:
        check_file_size(0, settings)
    assert info.value.code is IngestErrorCode.EMPTY_FILE


def test_probe_rejects_large_file_before_reading(tmp_path: Path) -> None:
    path = tmp_path / "big.pdf"
    path.write_bytes(b"%PDF-1.7\n" + b"0" * (MB + 10))
    with pytest.raises(IngestError) as info:
        reader.probe(path, Settings(max_file_mb=1))
    assert info.value.code is IngestErrorCode.TOO_LARGE


@pytest.mark.parametrize("name", ["multi_invoice.pdf", "scan_two_pages.tiff"])
def test_page_limit(synthetic_dir: Path, name: str) -> None:
    with pytest.raises(IngestError) as info:
        reader.probe(synthetic_dir / name, Settings(max_pdf_pages=1))
    assert info.value.code is IngestErrorCode.TOO_MANY_PAGES
    assert reader.probe(synthetic_dir / name, Settings(max_pdf_pages=10)).page_count >= 2
