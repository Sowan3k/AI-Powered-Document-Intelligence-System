"""Spreadsheet readers: .xlsx (openpyxl), .xls (xlrd) and CSV.

Every sheet is read. Merged cells take the value of their top-left cell, so a
merged header or a merged supplier name applies to every cell it covers.
"""

import csv
import io
import logging
from pathlib import Path
from typing import BinaryIO

import openpyxl
import xlrd

from app.ingest.errors import IngestError, IngestErrorCode
from app.ingest.schemas import SheetContent
from app.ingest.table import Row, build_sheet, cell_text
from app.ingest.textfile import decode, detect_delimiter

logger = logging.getLogger(__name__)


def _fill_merged(grid: list[list[object]], ranges: list[tuple[int, int, int, int]]) -> None:
    """Copy the top-left value into every cell of each merged range (0-based, end exclusive)."""
    for r0, r1, c0, c1 in ranges:
        if r0 >= len(grid):
            continue
        value = grid[r0][c0] if c0 < len(grid[r0]) else None
        for r in range(r0, min(r1, len(grid))):
            row = grid[r]
            if len(row) < c1:
                row.extend([None] * (c1 - len(row)))
            for c in range(c0, c1):
                row[c] = value


def read_xlsx(path: Path) -> list[SheetContent]:
    with path.open("rb") as fh:
        return _read_xlsx(fh)


def _read_xlsx(fh: BinaryIO) -> list[SheetContent]:
    try:
        # A file handle, not a path: openpyxl checks the extension of a path, and
        # file names are never trusted. Normal mode, because read_only mode
        # cannot see merged cells.
        wb = openpyxl.load_workbook(fh, data_only=True)
    except Exception as exc:
        logger.info("xlsx open failed: %s", type(exc).__name__)
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the workbook cannot be opened") from None
    try:
        sheets = []
        for index, ws in enumerate(wb.worksheets):
            grid: list[list[object]] = [list(row) for row in ws.iter_rows(values_only=True)]
            ranges = [
                (m.min_row - 1, m.max_row, m.min_col - 1, m.max_col) for m in ws.merged_cells.ranges
            ]
            _fill_merged(grid, ranges)
            sheets.append(build_sheet(index, ws.title, [[cell_text(v) for v in r] for r in grid]))
        return sheets
    finally:
        wb.close()


def _xls_value(book: xlrd.Book, cell: xlrd.sheet.Cell) -> object:
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate_as_datetime(cell.value, book.datemode)
        except (ValueError, OverflowError, xlrd.xldate.XLDateError):
            return cell.value
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return None
    return cell.value


def read_xls(path: Path) -> list[SheetContent]:
    try:
        book = xlrd.open_workbook(path, formatting_info=True, on_demand=True)
    except Exception as exc:
        logger.info("xls open failed: %s", type(exc).__name__)
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the workbook cannot be opened") from None
    try:
        sheets = []
        for index in range(book.nsheets):
            sh = book.sheet_by_index(index)
            grid: list[list[object]] = [
                [_xls_value(book, sh.cell(r, c)) for c in range(sh.ncols)] for r in range(sh.nrows)
            ]
            _fill_merged(grid, list(sh.merged_cells))
            sheets.append(build_sheet(index, sh.name, [[cell_text(v) for v in r] for r in grid]))
            book.unload_sheet(index)
        return sheets
    except IngestError:
        raise
    except Exception as exc:
        logger.info("xls read failed: %s", type(exc).__name__)
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the workbook cannot be read") from None
    finally:
        book.release_resources()


def read_csv(path: Path) -> list[SheetContent]:
    decoded = decode(path.read_bytes())
    if decoded is None:
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the CSV file is not readable text")
    text, encoding = decoded
    delimiter = detect_delimiter(text)
    if delimiter is None:
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the CSV file has no clear columns")
    try:
        grid: list[Row] = [
            [cell_text(v) for v in row]
            for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
        ]
    except csv.Error:
        raise IngestError(IngestErrorCode.CORRUPTED_FILE, "the CSV file cannot be parsed") from None
    logger.info("csv read: encoding=%s delimiter=%r rows=%d", encoding, delimiter, len(grid))
    return [build_sheet(0, "csv", grid)]
