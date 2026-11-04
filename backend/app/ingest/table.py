"""Turn a raw grid of cells into a SheetContent: drop empty rows, find the header."""

import re
from datetime import date, datetime, time
from decimal import Decimal

from app.ingest.schemas import SheetContent

HEADER_SCAN_ROWS = 20
HEADER_WORDS = {
    "invoice", "inv", "number", "no", "date", "supplier", "vendor", "seller", "customer",
    "client", "buyer", "bill", "description", "item", "qty", "quantity", "price", "unit",
    "rate", "amount", "subtotal", "tax", "vat", "gst", "total", "currency", "due", "reference",
}  # fmt: skip
NUMBER = re.compile(r"^[\s(+-]*[$€£¥৳]?\s*[\d.,]+\s*%?\)?$")
DATE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}")

Cell = str | None
Row = list[Cell]


def cell_text(value: object) -> Cell:
    """Convert a spreadsheet value to text without losing precision."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat()
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(Decimal(repr(value)), "f")
    if isinstance(value, int | Decimal):
        return str(value)
    text = " ".join(str(value).split())
    return text or None


def _is_data_value(cell: str) -> bool:
    return bool(NUMBER.match(cell) or DATE.match(cell))


def _header_score(row: Row) -> int | None:
    cells = [c for c in row if c]
    if len(cells) < 2:
        return None
    labels = [c for c in cells if not _is_data_value(c)]
    if len(labels) < 0.8 * len(cells):
        return None
    words = {w for c in labels for w in re.findall(r"[a-z]+", c.lower())}
    return len(labels) + 2 * len(words & HEADER_WORDS)


def detect_header(rows: list[Row]) -> int | None:
    """Index of the header row among the first rows, or None if there is none."""
    best: tuple[int, int] | None = None
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        score = _header_score(row)
        if score is not None and (best is None or score > best[0]):
            best = (score, i)
    return best[1] if best else None


def _clean_headers(raw: Row, width: int) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for j in range(width):
        name = (raw[j] if j < len(raw) else None) or f"column_{j + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        headers.append(name)
    return headers


def build_sheet(index: int, name: str, grid: list[Row]) -> SheetContent:
    """`grid` is every source row in order; row i is source row i + 1."""
    numbered = [(i + 1, row) for i, row in enumerate(grid) if any(c for c in row)]
    width = max(
        (max((j + 1 for j, c in enumerate(r) if c), default=0) for _, r in numbered), default=0
    )
    rows = [row[:width] + [None] * (width - len(row[:width])) for _, row in numbered]
    header_at = detect_header(rows)
    if header_at is None:
        headers = _clean_headers([], width)
        body, numbers, header_row = rows, [n for n, _ in numbered], None
    else:
        headers = _clean_headers(rows[header_at], width)
        body = rows[header_at + 1 :]
        numbers = [n for n, _ in numbered[header_at + 1 :]]
        header_row = numbered[header_at][0]
    return SheetContent(
        sheet_index=index,
        sheet_name=name,
        header_row=header_row,
        headers=headers,
        rows=body,
        row_numbers=numbers,
    )
