"""Encoding and delimiter detection for CSV files."""

import csv
import io

from charset_normalizer import from_bytes

DELIMITERS = (",", ";", "\t", "|")
SAMPLE_LINES = 30


def decode(data: bytes) -> tuple[str, str] | None:
    """Return (text, encoding), or None if the bytes do not look like text."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            return None
    if b"\x00" in data:
        return None  # binary
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    best = from_bytes(data).best()
    if best is None:
        return None
    return str(best), best.encoding


def decode_prefix(data: bytes) -> str | None:
    """Decode the start of a file, tolerating a multibyte character cut at the end."""
    for cut in range(4):
        result = decode(data[: len(data) - cut] if cut else data)
        if result is not None:
            return result[0]
    return None


def detect_delimiter(text: str) -> str | None:
    """Pick the delimiter that splits the first lines into the same column count."""
    lines = [line for line in text.splitlines() if line.strip()][:SAMPLE_LINES]
    if len(lines) < 2:
        return None
    best: tuple[int, int, str] | None = None
    for delimiter in DELIMITERS:
        counts = [
            len(row) for row in csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
        ]
        width = max(set(counts), key=counts.count)
        agreeing = counts.count(width)
        if width < 2 or agreeing < max(2, len(counts) // 2):
            continue
        score = (agreeing, width, delimiter)
        if best is None or score[:2] > best[:2]:
            best = score
    return best[2] if best else None
