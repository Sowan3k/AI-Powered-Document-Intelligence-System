# Evaluation

How well DocIntel reads, checks and processes invoices, measured on a labelled dataset with the real Gemini models. Every number below comes from a run of the "Evaluation" GitHub Actions workflow, which runs `eval/run_eval.py` with the `GEMINI_API_KEY` secret. The method is in D51; the dataset generator in D13 and D35.

Results from evaluation run 3 are added here when it finishes.

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
