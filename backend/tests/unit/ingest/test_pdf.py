"""PDF reader: digital text, page batches, scanned page detection, broken files."""

from pathlib import Path

import pymupdf
import pytest

from app.core.config import Settings
from app.db.enums import PageMethod
from app.ingest import pdf
from app.ingest.errors import IngestError, IngestErrorCode


def test_digital_pages_keep_text_and_order(synthetic_dir: Path) -> None:
    pages = list(pdf.iter_pages(synthetic_dir / "multi_invoice.pdf", Settings()))
    assert [p.page_number for p in pages] == [1, 2, 3, 4]
    assert all(p.method is PageMethod.DIGITAL and p.ocr_confidence is None for p in pages)
    assert all("INV-2026-" in p.text for p in pages)


def test_batch_size_does_not_change_the_result(synthetic_dir: Path) -> None:
    path = synthetic_dir / "multi_invoice.pdf"
    one = list(pdf.iter_pages(path, Settings(pdf_page_batch_size=1)))
    many = list(pdf.iter_pages(path, Settings(pdf_page_batch_size=50)))
    assert one == many


def test_pages_stream_lazily(synthetic_dir: Path) -> None:
    pages = pdf.iter_pages(synthetic_dir / "multi_invoice.pdf", Settings())
    assert next(pages).page_number == 1  # nothing else is read yet


def test_is_scanned() -> None:
    assert pdf.is_scanned("", 25)
    assert pdf.is_scanned("  - 1 -  \n", 25)
    assert not pdf.is_scanned("Invoice INV-001 Total 120.00 USD", 25)


@pytest.mark.tesseract
def test_scanned_pages_go_to_ocr(synthetic_dir: Path) -> None:
    pages = list(pdf.iter_pages(synthetic_dir / "scanned_light.pdf", Settings()))
    assert [p.method for p in pages] == [PageMethod.OCR, PageMethod.OCR]
    assert all(p.ocr_confidence is not None and p.ocr_confidence > 60 for p in pages)
    assert "INVOICE" in pages[0].text


@pytest.mark.tesseract
def test_mixed_pdf_uses_ocr_only_where_needed(tmp_path: Path, synthetic_dir: Path) -> None:
    mixed = pymupdf.open(synthetic_dir / "digital_classic_0.pdf")
    mixed.insert_pdf(pymupdf.open(synthetic_dir / "scanned_light.pdf"), from_page=0, to_page=0)
    mixed.save(tmp_path / "mixed.pdf")
    pages = list(pdf.iter_pages(tmp_path / "mixed.pdf", Settings()))
    assert [p.method for p in pages] == [PageMethod.DIGITAL, PageMethod.OCR]


def test_blank_page_has_no_text(tmp_path: Path) -> None:
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "blank.pdf")
    settings = Settings(scanned_page_min_chars=0)  # keep it digital, no OCR needed
    [page] = pdf.iter_pages(tmp_path / "blank.pdf", settings)
    assert page.text == "" and page.method is PageMethod.DIGITAL


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("truncated.pdf", IngestErrorCode.CORRUPTED_FILE),
        ("garbage.pdf", IngestErrorCode.CORRUPTED_FILE),
        ("encrypted.pdf", IngestErrorCode.ENCRYPTED_PDF),
    ],
)
def test_broken_pdfs(synthetic_dir: Path, name: str, code: IngestErrorCode) -> None:
    with pytest.raises(IngestError) as info:
        pdf.count_pages(synthetic_dir / name, Settings())
    assert info.value.code is code


def test_encrypted_pdf_message_names_no_password(synthetic_dir: Path) -> None:
    with pytest.raises(IngestError) as info:
        list(pdf.iter_pages(synthetic_dir / "encrypted.pdf", Settings()))
    assert "password protected" in info.value.message
