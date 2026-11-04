# Evaluation

How well DocIntel reads, checks and processes invoices, measured on a labelled dataset with the real Gemini models. Every number below comes from a run of the "Evaluation" GitHub Actions workflow, which runs `eval/run_eval.py` with the `GEMINI_API_KEY` secret. The method is in D51; the dataset generator in D13 and D35.

## Results

From evaluation run 4 on 4 November 2026 ([GitHub Actions run 41842715059](https://github.com/Sowan3k/AI-Powered-Document-Intelligence-System/actions/runs/41842715059)), with `gemini-3.5-flash-lite` for text, `gemini-3.8-flash` for vision and `gemini-embedding-2` for embeddings, on the scale 2 dataset: 36 files and 87 labelled invoices. The full JSON report is kept as the run's `evaluation-report` artifact.

### Extraction

| Field | Accuracy |
|---|---|
| Invoice number | 100% |
| Invoice date | 100% |
| Supplier | 100% |
| Customer | 100% |
| Subtotal | 100% |
| Tax | 100% |
| Total | 100% |
| Currency | 100% |
| **All fields (696 values)** | **100%** |

- Invoices found: 87 of 87, each with its exact page range, including the long statement's two-page invoices that cross window edges.
- Line items: 211 extracted, 211 expected. Precision 100%, recall 100%, F1 100%.
- The three layouts cover US amounts with a dollar sign, amounts without a symbol and day-first dates, and European amounts with comma decimals. All parsed to the exact values.

### Documents

| Outcome | Files |
|---|---|
| Completed | 27 |
| Correctly rejected with the right code | 9 of 9 (`CORRUPTED_FILE` 4, `EMPTY_FILE` 2, `UNSUPPORTED_TYPE` 2, `ENCRYPTED_PDF` 1) |
| Failed | 0 |

Every job finished on its first attempt.

### Validation

| Planted error | Rule | Caught |
|---|---|---|
| Total does not match subtotal plus tax | R05 | 2 of 2 |
| Line amounts do not add up to the subtotal | R03 | 1 of 1 |
| Quantity times unit price differs from the amount | R04 | 1 of 1 |
| Tax missing | R01 (warning) | 1 of 1 |
| Customer missing | R01 (warning) | 1 of 1 |
| Invoice number missing | R01 | 1 of 1 |
| Date in the future | R08 | 1 of 1 |
| Duplicate (same invoice, supplier spelled differently) | R06 | 1 of 1 |
| Possible duplicate (new number, same supplier, date, total) | R07 | 1 of 1 |

**Detection: 10 of 10 (100%). False flags: 1 of 77 clean invoices (1.3%)**, one R04 error. Every line amount on that invoice was read correctly (line scoring matched all 211 amounts), so the flag most likely comes from a misread quantity or unit price. That is the case R04 exists for: the arithmetic catches a reading error the model made with confidence, and a person checks it.

### Speed

| Path | Documents | Mean per document | p95 per document | Mean per page |
|---|---|---|---|---|
| Digital PDF | 17 | 41.7 s | 54.4 s | 25.2 s |
| OCR (scans read by Tesseract) | 4 | 33.0 s | 44.6 s | 22.2 s |
| Vision (weak scan) | 1 | 66.0 s | 66.0 s | 66.0 s |
| Spreadsheet | 5 | 0.4 s | 0.4 s | n/a |

Pages by method: 63 digital, 6 OCR, 1 vision. The whole run took 15 minutes.

These times are dominated by the deliberate pacing of model calls to stay under the free-tier quota (12 calls a minute, D53), not by processing. Each PDF needs at least one extraction call and one embedding call, and documents wait in line for the quota. Spreadsheets need no extraction call. The vision page also waited for the overloaded `gemini-3.8-flash`, which answered HTTP 503, before the text model read it (D44). On a paid tier, raising `LLM_CALLS_PER_MINUTE` changes these numbers directly.

### Tokens

| | Tokens |
|---|---|
| Total for the run | 75,048 |
| Mean per completed document | 2,780 |
| 95th percentile per document | 7,023 (the 37-page statement) |
| Extraction | 69,900 in 27 calls |
| Embeddings | 3,776 in 27 calls |
| Vision transcription | 1,372 in 1 call |

A single-page invoice uses about 1,400 tokens for extraction and embedding together. No price is printed because the per-token price of these models was not confirmed; the indicative cost of a document is its token count times the current Gemini price per token.

## What the earlier runs found

The first real runs were not clean, and each one led to a fix that this run measures:

| Run | Result | Cause and fix |
|---|---|---|
| 1 | Completed documents 100% correct, but 9 of 26 failed; 26 minutes | Calls faster than the free-tier quota, retries too short to wait it out. The client now paces calls and honours the server's retry delay (D53). A truncated PDF was "repaired" by MuPDF into empty pages that went to the overloaded vision model; damaged pages now fail the file as `CORRUPTED_FILE`, and blank pages skip OCR and vision (D52). |
| 2 | Cancelled to include the next fixes | |
| 3 | No rate-limit failures, all broken files correct, but all 10 multi-invoice documents failed | The SDK sent a list of strings as one multi-part content, and the embedding model returned one vector. One request per text now, checked with the real SDK in a unit test (D54). |
| 4 | This report | |

Before these runs, the manual smoke test had also found the vision model overloaded, which led to the fallback chain in D44.

## Weak spots

- **Synthetic data.** 100% on clean synthetic layouts says the pipeline is sound; it does not predict accuracy on real invoices, which have noisier layouts, logos, stamps and handwriting.
- **The vision path is barely measured.** Only one page needed vision, and the vision model was overloaded in every run, so that page was read by the text model through the fallback. The quality of `gemini-3.8-flash` on poor scans is untested.
- **Line items are matched by amount.** A misread quantity or unit price does not lower the line item score; R04 catches it instead, as it did once here.
- **Speed under the free tier.** About 40 seconds per document is the quota at work. Large batches will take a long time on the free tier.

## Scale check: a 1,000-page PDF

The brief says PDFs can run to about 1,000 pages. Measured in the coding sandbox on 4 November with the real readers (no model calls), using `eval/generate/synth` to build the files:

| File | Pages | Read time | Per page | Peak memory | Memory after the last page |
|---|---|---|---|---|---|
| Digital PDF | 1,000 | 2.6 s | 2.6 ms | 160 MB (145 MB at start) | flat |
| Scanned PDF (light noise, 300 DPI OCR) | 30 | 23.8 s | 0.79 s | 211 MB | 145 MB |

- Pages stream in batches, so a digital PDF adds about 15 MB however long it is.
- The first scanned run peaked at 290 MB, because MuPDF kept each decoded page image in its cache until the end of a 20-page batch. The cache is now trimmed after every scanned page, which brought the peak to 211 MB and keeps memory flat. That matters on Render's 512 MB instance, where the API process runs beside the worker.
- A 1,000-page document needs 143 extraction calls (windows of 8 pages, 1 page of overlap). At the free-tier pace of 12 calls a minute (D53) that is about 12 minutes of model calls, plus about 13 minutes of OCR if every page is scanned (at this sandbox's CPU speed; Render's free CPU is slower). The document page shows progress as "window 12 of 143" while it runs.
- Not measured: a full 1,000-page run through Gemini, which would spend a large share of the free-tier daily quota.

## The dataset

`eval/generate/synth` builds the dataset with a fixed seed, and writes ground truth JSON beside each file. At scale 2 it holds 36 files:

| Group | Files | Tests |
|---|---|---|
| Digital PDFs | 6 single invoices in three layouts (US, "tax invoice" with day-first dates, European with comma decimals) | Field reading across layouts and number formats |
| Planted errors | 6 PDFs: wrong total, wrong line sum, wrong line amount, missing tax, missing customer, a date in 2099 | Validation rules R05, R03, R04, R01, R08 |
| Duplicates | The first classic invoice again in another layout with the supplier spelled "LIMITED"; and a near duplicate (same supplier, date and total, new number) | R06 and R07 |
| Multi-invoice PDF | 8 invoices on 8 pages | Segmentation |
| Long statement | 30 invoices on 37 pages; every fourth spans two pages and its second page repeats no number | Window edges and timing (D39) |
| Scans | A 2-page scanned PDF with light noise and a small tilt, a heavy-noise JPEG (blur, noise, strong JPEG), a clean PNG, a 2-page TIFF | OCR, deskew, the vision fallback |
| Spreadsheets | A two-sheet `.xlsx` (merged title, blank rows), an `.xls`, a CSV, a semicolon CSV in cp1252 | Header detection, encodings, column mapping |
| Reconciliation | A 4-invoice PDF and a workbook with one changed total, one row without a number and one extra invoice | Cross-verification |
| Broken files | Truncated, garbage and encrypted PDFs, an empty file, a whitespace file, prose named `.pdf`, a Word file named `.xlsx`, a damaged workbook, a truncated PNG | Failure codes |

Several invoices appear in more than one file on purpose (one invoice as a PDF, a scan and a TIFF; the registers in three spreadsheet formats). That is why duplicate rules are left out of the false flag rate.

## How it is scored

- **Fields.** Each true invoice is paired with a stored one by normalised number. Values are compared after normalisation: invoice numbers without punctuation, supplier names without case or company suffix, customer names without case, money as exact decimals, dates as dates, currency as ISO codes. An invoice the system missed counts as wrong on every field.
- **Line items.** A line matches when an extracted line has the same amount. Precision, recall and F1 over all PDF and image invoices; the spreadsheet registers carry no line columns.
- **Documents.** Completed, failed by cause, and each broken file against the code it must get.
- **Timing.** From the processing events: job start to completion, per document and per page, split by path (digital, OCR, vision, spreadsheet). Mean and 95th percentile. Times include the deliberate pacing of model calls (D53).
- **Validation.** Each planted error must trigger its rule. The false flag rate counts clean invoices with any error-level issue, without R06 and R07.
- **Tokens.** Summed from the `llm_call` events, including embeddings. No cost is printed: the price of these models was not confirmed, so tokens are the honest unit.

## Limits of this evaluation

1. The invoices are synthetic and cleaner than real ones: neat fonts, consistent labels, no stamps, handwriting, folds or coffee stains. Real accuracy will be lower. No real invoices were added (licensing and personal data).
2. The dataset is small (dozens of invoices, not thousands), so one error moves a percentage a lot.
3. Timing comes from GitHub's runners, not Render's free instance, which has less CPU; OCR there will be slower.
4. The free-tier vision model was overloaded during every run, so scanned pages that needed vision were read by the text model through the fallback (D44), and their timing includes the wait.
