"""File type detection follows the bytes, never the name."""

import zipfile
from pathlib import Path

import pytest

from app.core.config import Settings
from app.ingest.detect import OLE_MAGIC, detect_kind
from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.schemas import FileKind


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def code_of(path: Path, settings: Settings | None = None) -> IngestErrorCode:
    with pytest.raises(IngestError) as info:
        detect_kind(path, settings or Settings())
    return info.value.code


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("digital_classic_0.pdf", FileKind.PDF),
        ("scan_heavy.jpg", FileKind.JPEG),
        ("scan_clean.png", FileKind.PNG),
        ("scan_two_pages.tiff", FileKind.TIFF),
        ("register.xlsx", FileKind.XLSX),
        ("register.xls", FileKind.XLS),
        ("register.csv", FileKind.CSV),
        ("register_semicolon_cp1252.csv", FileKind.CSV),
        ("renamed_png.pdf", FileKind.PNG),  # a PNG with a .pdf name is a PNG
    ],
)
def test_detects_by_magic_bytes(synthetic_dir: Path, name: str, kind: FileKind) -> None:
    assert detect_kind(synthetic_dir / name, Settings()) is kind


def test_extension_is_ignored(tmp_path: Path, synthetic_dir: Path) -> None:
    data = (synthetic_dir / "digital_classic_0.pdf").read_bytes()
    assert detect_kind(write(tmp_path, "invoice.xlsx", data), Settings()) is FileKind.PDF
    assert detect_kind(write(tmp_path, "no_extension", data), Settings()) is FileKind.PDF


def test_pdf_header_after_leading_junk(tmp_path: Path) -> None:
    assert detect_kind(write(tmp_path, "a", b"\r\n  %PDF-1.4\n..."), Settings()) is FileKind.PDF


def test_empty_and_whitespace_files(tmp_path: Path) -> None:
    assert code_of(write(tmp_path, "a.pdf", b"")) is IngestErrorCode.EMPTY_FILE
    assert code_of(write(tmp_path, "b.csv", b" \r\n\t\n")) is IngestErrorCode.EMPTY_FILE


def test_unsupported_content(tmp_path: Path) -> None:
    assert code_of(write(tmp_path, "a.pdf", b"just one line of prose")) is (
        IngestErrorCode.UNSUPPORTED_TYPE
    )
    assert code_of(write(tmp_path, "b.gif", b"GIF89a" + b"\x00" * 64)) is (
        IngestErrorCode.UNSUPPORTED_TYPE
    )
    assert code_of(write(tmp_path, "c.exe", b"MZ\x90\x00" + bytes(range(256)))) is (
        IngestErrorCode.UNSUPPORTED_TYPE
    )


def test_zip_that_is_not_a_workbook(synthetic_dir: Path) -> None:
    assert code_of(synthetic_dir / "letter.xlsx") is IngestErrorCode.UNSUPPORTED_TYPE


def test_broken_zip(tmp_path: Path) -> None:
    path = write(tmp_path, "a.xlsx", b"PK\x03\x04" + b"\x00" * 40)
    assert code_of(path) is IngestErrorCode.CORRUPTED_FILE


def test_zip_bomb_is_too_large(tmp_path: Path) -> None:
    settings = Settings(max_unzipped_mb=1)
    bomb = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (2 * 1024 * 1024))
    assert bomb.stat().st_size < 100_000
    assert code_of(bomb, settings) is IngestErrorCode.TOO_LARGE


def test_ole_files(tmp_path: Path) -> None:
    def ole(stream: str) -> bytes:
        return OLE_MAGIC + b"\x00" * 500 + stream.encode("utf-16-le") + b"\x00" * 100

    encrypted = write(tmp_path, "locked.xlsx", ole("EncryptedPackage"))
    assert code_of(encrypted) is IngestErrorCode.ENCRYPTED_FILE
    word = write(tmp_path, "old.doc", ole("WordDocument"))
    assert code_of(word) is IngestErrorCode.UNSUPPORTED_TYPE


def test_csv_needs_consistent_columns(tmp_path: Path) -> None:
    good = write(tmp_path, "a.txt", b"a|b|c\n1|2|3\n4|5|6\n")
    assert detect_kind(good, Settings()) is FileKind.CSV
    utf16 = write(tmp_path, "b.csv", "x\ty\n1\t2\n3\t4\n".encode("utf-16"))
    assert detect_kind(utf16, Settings()) is FileKind.CSV
