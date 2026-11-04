"""Files that must fail cleanly, each with the failure code it must produce."""

import zipfile
from pathlib import Path

import pymupdf


def truncated_pdf(good: bytes, path: Path, keep: float = 0.3) -> None:
    """Cut a PDF short. PyMuPDF repairs small cuts, so cut deep into the file."""
    path.write_bytes(good[: max(16, int(len(good) * keep))])


def garbage_pdf(path: Path) -> None:
    """A PDF header followed by nothing usable."""
    path.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 8)


def encrypted_pdf(good: bytes, path: Path, password: str = "fixture-only") -> None:
    doc = pymupdf.open(stream=good, filetype="pdf")
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    doc.close()


def empty_file(path: Path) -> None:
    path.write_bytes(b"")


def whitespace_file(path: Path) -> None:
    path.write_bytes(b"   \n\n\t \n")


def text_named_pdf(path: Path) -> None:
    """Plain prose with a .pdf extension: no magic bytes, no columns."""
    path.write_text("This is a plain note, not an invoice.\nIt only pretends to be a PDF.\n")


def docx_like(path: Path) -> None:
    """A ZIP that is a Word file, not a workbook."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<document/>")


def corrupted_xlsx(path: Path) -> None:
    """Valid ZIP with a workbook part that is not XML."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", "not xml at all")


def truncated_png(good: bytes, path: Path) -> None:
    path.write_bytes(good[: len(good) // 3])
