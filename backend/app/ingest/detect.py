"""File type detection by magic bytes. The file name and extension are never trusted."""

import zipfile
from pathlib import Path

from app.core.config import Settings
from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.limits import MB
from app.ingest.schemas import FileKind
from app.ingest.textfile import decode_prefix, detect_delimiter

HEAD_BYTES = 8192
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _utf16(name: str) -> bytes:
    return name.encode("utf-16-le")


def detect_kind(path: Path, settings: Settings) -> FileKind:
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(HEAD_BYTES)
    if size == 0 or (size <= HEAD_BYTES and not head.strip(b" \t\r\n\x00")):
        raise IngestError(IngestErrorCode.EMPTY_FILE, "the file is empty")

    # The PDF header may follow a little junk; readers accept it within 1 KB.
    if b"%PDF-" in head[:1024]:
        return FileKind.PDF
    if head.startswith(b"\xff\xd8\xff"):
        return FileKind.JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileKind.PNG
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return FileKind.TIFF
    if head.startswith(b"PK\x03\x04"):
        return _zip_kind(path, settings)
    if head.startswith(OLE_MAGIC):
        return _ole_kind(path)
    if _looks_like_csv(head):
        return FileKind.CSV
    raise IngestError(IngestErrorCode.UNSUPPORTED_TYPE, "the file type is not supported")


def _zip_kind(path: Path, settings: Settings) -> FileKind:
    """A ZIP is an .xlsx only if it holds a workbook part."""
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError):
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the archive cannot be read") from None
    names = {info.filename for info in infos}
    if "xl/workbook.xml" not in names:
        raise IngestError(IngestErrorCode.UNSUPPORTED_TYPE, "the file type is not supported")
    if sum(info.file_size for info in infos) > settings.max_unzipped_mb * MB:
        raise IngestError(
            IngestErrorCode.TOO_LARGE,
            f"the workbook is larger than {settings.max_unzipped_mb} MB once unpacked",
        )
    return FileKind.XLSX


def _ole_kind(path: Path) -> FileKind:
    """OLE2 holds .xls, .doc and password-protected .xlsx. Look at the stream names."""
    data = path.read_bytes()
    if _utf16("EncryptedPackage") in data:
        raise IngestError(IngestErrorCode.ENCRYPTED_FILE, "the workbook is password protected")
    if _utf16("Workbook") in data or _utf16("Book\x00") in data:
        return FileKind.XLS
    raise IngestError(IngestErrorCode.UNSUPPORTED_TYPE, "the file type is not supported")


def _looks_like_csv(head: bytes) -> bool:
    text = decode_prefix(head)
    return text is not None and detect_delimiter(text) is not None
