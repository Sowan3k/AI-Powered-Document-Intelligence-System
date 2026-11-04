# Test fixtures

Reader tests do not use committed binary files. The synthetic generator in
`eval/generate/synth` builds them once per test run, with a fixed seed, into a
temporary folder (`synthetic_dir` in `tests/conftest.py`). See DECISIONS.md D35.

The set holds digital PDFs in three layouts, planted-error invoices, a
multi-invoice PDF, scans (PDF, JPEG, PNG, two-page TIFF), `.xlsx`, `.xls` and CSV
registers, and broken files: truncated, garbage and encrypted PDFs, empty and
whitespace files, prose renamed to `.pdf`, a Word ZIP named `.xlsx`, a damaged
workbook and a truncated PNG. `manifest.json` records what each must produce.

To look at the files:

    cd eval/generate && python -m synth --out /tmp/docintel-fixtures
