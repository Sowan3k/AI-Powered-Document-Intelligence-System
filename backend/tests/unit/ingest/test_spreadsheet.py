"""Spreadsheet and CSV readers, header detection, merged cells and empty rows."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from app.ingest import spreadsheet, textfile
from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.table import build_sheet, cell_text, detect_header


def test_xlsx_reads_every_sheet(synthetic_dir: Path) -> None:
    october, november = spreadsheet.read_xlsx(synthetic_dir / "register.xlsx")
    assert (october.sheet_name, november.sheet_name) == ("October", "November")
    assert october.header_row == 3  # title row and blank row skipped
    assert october.headers[:3] == ["Invoice No", "Invoice Date", "Supplier"]
    assert october.row_count == 5
    # The blank row inside the data is dropped, and source row numbers stay true.
    assert october.row_numbers == [4, 5, 7, 8, 9]
    assert all(len(row) == len(october.headers) for row in october.rows)
    first = dict(zip(october.headers, october.rows[0], strict=True))
    assert first["Invoice No"].startswith("INV-2026-")
    date.fromisoformat(first["Invoice Date"])  # dates come out as ISO text


def test_xls_reads_dates_and_merged_title(synthetic_dir: Path) -> None:
    [sheet] = spreadsheet.read_xls(synthetic_dir / "register.xls")
    assert sheet.header_row == 3
    assert sheet.row_count == 5
    date.fromisoformat(sheet.rows[0][1])


def test_merged_cells_fill_their_range(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Supplier", "Invoice No", "Total"])
    ws.append(["Acme Traders Ltd", "A-1", 10])
    ws.append([None, "A-2", 20])
    ws.merge_cells("A2:A3")  # one supplier cell covering two invoices
    wb.save(tmp_path / "merged.xlsx")
    [sheet] = spreadsheet.read_xlsx(tmp_path / "merged.xlsx")
    assert [row[0] for row in sheet.rows] == ["Acme Traders Ltd", "Acme Traders Ltd"]


def test_corrupted_workbooks(synthetic_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(IngestError) as info:
        spreadsheet.read_xlsx(synthetic_dir / "corrupted.xlsx")
    assert info.value.code is IngestErrorCode.CORRUPTED_FILE
    bad = tmp_path / "bad.xls"
    bad.write_bytes((synthetic_dir / "register.xls").read_bytes()[:2000])
    with pytest.raises(IngestError) as info:
        spreadsheet.read_xls(bad)
    assert info.value.code is IngestErrorCode.CORRUPTED_FILE


def test_csv_semicolon_and_cp1252(synthetic_dir: Path) -> None:
    [sheet] = spreadsheet.read_csv(synthetic_dir / "register_semicolon_cp1252.csv")
    assert sheet.header_row == 1 and sheet.row_count == 3
    assert "Café Lumière" in sheet.rows[0]


def test_csv_with_bom_quotes_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    text = 'Invoice No,Supplier,Total\r\n\r\nA-1,"Acme, Traders",10.50\r\nA-2,Delta,"1,200.00"\r\n'
    path.write_bytes(b"\xef\xbb\xbf" + text.encode())
    [sheet] = spreadsheet.read_csv(path)
    assert sheet.headers == ["Invoice No", "Supplier", "Total"]  # no BOM in the first header
    assert sheet.rows == [["A-1", "Acme, Traders", "10.50"], ["A-2", "Delta", "1,200.00"]]
    assert sheet.row_numbers == [3, 4]


def test_detect_delimiter() -> None:
    assert textfile.detect_delimiter("a;b;c\n1;2;3\n4;5;6") == ";"
    assert textfile.detect_delimiter("a\tb\n1\t2\n") == "\t"
    assert textfile.detect_delimiter("a,b\n1,2\n") == ","
    assert textfile.detect_delimiter("just prose here\nand more prose") is None


def test_decode() -> None:
    assert textfile.decode("Café".encode()) == ("Café", "utf-8")
    assert textfile.decode("x\ny".encode("utf-16"))[0] == "x\ny"  # type: ignore[index]
    assert textfile.decode(b"\x00\x01\x02") is None


def test_header_detection_skips_titles_and_number_rows() -> None:
    rows = [
        ["Invoice register 2026", None, None],
        ["Invoice No", "Date", "Total"],
        ["A-1", "2026-01-02", "10.00"],
    ]
    assert detect_header(rows) == 1
    assert detect_header([["1", "2"], ["3", "4"]]) is None


def test_sheet_without_header_gets_column_names() -> None:
    sheet = build_sheet(0, "s", [["1", "2"], [None, None], ["3", "4"]])
    assert sheet.header_row is None
    assert sheet.headers == ["column_1", "column_2"]
    assert sheet.row_numbers == [1, 3]


def test_duplicate_and_blank_headers() -> None:
    sheet = build_sheet(0, "s", [["Total", None, "Total", "Supplier"], ["1", "x", "2", "Acme"]])
    assert sheet.headers == ["Total", "column_2", "Total_2", "Supplier"]


def test_empty_sheet() -> None:
    sheet = build_sheet(0, "empty", [[None, None], []])
    assert (sheet.headers, sheet.rows, sheet.row_count) == ([], [], 0)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, None),
        ("  Acme   Ltd ", "Acme Ltd"),
        ("   ", None),
        (12, "12"),
        (12.0, "12"),
        (0.1, "0.1"),
        (1e-5, "0.00001"),
        (1234.5, "1234.5"),
        (Decimal("3.3333"), "3.3333"),
        (True, "TRUE"),
        (datetime(2026, 3, 4), "2026-03-04"),
        (datetime(2026, 3, 4, 9, 30), "2026-03-04T09:30:00"),
        (date(2026, 3, 4), "2026-03-04"),
    ],
)
def test_cell_text(value: object, text: str | None) -> None:
    assert cell_text(value) == text


def test_readers_ignore_the_file_name(synthetic_dir: Path, tmp_path: Path) -> None:
    # The worker saves downloads without an extension; readers must not care.
    for name, read in (
        ("register.xlsx", spreadsheet.read_xlsx),
        ("register.xls", spreadsheet.read_xls),
        ("register.csv", spreadsheet.read_csv),
    ):
        plain = tmp_path / f"original-{name.split('.')[1]}"
        plain.write_bytes((synthetic_dir / name).read_bytes())
        assert read(plain)[0].row_count == 5
