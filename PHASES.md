# PHASES.md

Build plan for DocIntel. Each phase lists its goal, its checklist and its exit test. Dates are Dhaka time. Final deadline: 8 November 2026, 03:39. Target submission: 7 November 2026, 22:00.

If a phase runs late, cut scope inside that phase before touching the next one. A smaller system that works and is honestly measured beats a larger one that breaks in the demo.

---

## Phase 0: Setup and a deployed skeleton (4 Nov, morning)

Goal: an empty but working system is live on Render and Vercel before any real feature exists. Deployment problems surface on day one, not on day five.

Manual steps for Sowan (secrets go into dashboards only, never into chat or files):

- [x] Create the private GitHub repository and connect it to Claude Code
- [x] Create a Gemini API key in Google AI Studio and note the current Flash, vision and embedding model names (D31)
- [x] Create a Supabase project in the Singapore region, enable the `vector` extension, create a private storage bucket named `documents` (done by Sowan; `pg_trgm` also enabled, Data API disabled)
- [x] Create a Render web service from the repo (Docker runtime, Singapore region, free instance) and add the environment variables from `.env.example` (Blueprint, `docintel-api`)
- [x] Create a Vercel project for the `frontend` folder and add its environment variables (`docintel`)
- [x] Add `GEMINI_API_KEY` as a GitHub Actions secret (used only by the evaluation workflow; Sowan confirmed it on the repo's secrets page, 4 Nov)

Claude Code checklist:

- [x] Backend skeleton: FastAPI app, config from environment, `/api/health` endpoint that checks the database connection
- [x] SQLAlchemy models and the first Alembic migration for every table in the CLAUDE.md data model
- [x] `Dockerfile` that installs Tesseract and runs `start.sh` (API process plus worker process)
- [x] `docker-compose.yml` with backend, worker and a pgvector Postgres for reviewers who run locally
- [x] Frontend skeleton: Next.js app with one page that calls `/api/health`
- [x] GitHub Actions workflow: ruff, pytest, gitleaks
- [x] `docs/BRIEF.md` with the full assignment text

Exit test: the Vercel page shows "API healthy, database connected" from the live Render service.

**Exit test passed on 4 Nov 2026.** Sowan reported the live page working. Render logs show migrations ran, the worker started, and every `/api/health` call after the CORS update returned 200 (the endpoint returns 503 when the database is down).

---

## Phase 1: Document ingestion (4 Nov)

Goal: every accepted file type turns into one common internal structure (pages or sheets of text with metadata), and bad files fail cleanly.

- [x] File type detection by magic bytes for PDF, JPG, PNG, TIFF, XLSX, XLS, CSV
- [x] Upload limits from config: file size, files per batch, pages per PDF
- [x] Digital PDF reader with PyMuPDF, page by page, in batches
- [x] Scanned page detection: a page with almost no extractable text is rendered to an image and sent to OCR
- [x] Image cleanup with OpenCV: grayscale, deskew, denoise, threshold
- [x] Tesseract OCR with a per-page mean confidence score
- [x] Multi-page TIFF support
- [x] Spreadsheet reader: every sheet, header row detection, empty row and merged cell handling, CSV encoding and delimiter detection
- [x] Clear failure codes: `UNSUPPORTED_TYPE`, `CORRUPTED_FILE`, `ENCRYPTED_PDF`, `EMPTY_FILE`, `TOO_LARGE`, `TOO_MANY_PAGES` (plus `ENCRYPTED_FILE` and `TOO_MANY_FILES`, D33)
- [x] Synthetic dataset generator in `eval/generate/` (see Phase 6), built now because the tests need fixtures
- [x] Unit tests for each reader, including a truncated PDF, an empty file and a renamed file
- [x] Storage interface: Supabase Storage in production, local disk for compose and tests (D32)

Exit test: every fixture file produces either the expected text structure or the expected failure code.

**Exit test passed on 4 Nov 2026.** CI run 10: 147 tests passed with none skipped (Tesseract required), including the manifest test over 26 generated files. The Docker job built the image and ran the compose stack.

---

## Phase 2: AI information extraction (5 Nov)

Goal: page text and spreadsheet rows become validated invoice JSON with no invented values.

- [x] Pydantic schema for an invoice: invoice number, invoice date, supplier name, customer name, subtotal, tax, total, currency, line items. Each field holds a value, a confidence score and an evidence snippet
- [x] Gemini client module: structured JSON output, semaphore, retry with backoff, timeout, token logging per call
- [x] Extraction prompt that requires `null` for missing or unclear values and forbids guessing
- [x] Invoice segmentation for multi-invoice PDFs: process pages in overlapping windows, ask the model for invoices with page ranges, merge invoices that cross a window boundary
- [x] Evidence check in code: the invoice number and total must appear in the source text, otherwise lower the confidence and flag the field
- [x] Gemini vision fallback for pages where OCR confidence is below the configured threshold
- [x] Spreadsheet column mapping: match known header names by rule first; call the LLM once per sheet only when the rule cannot map a column; convert rows in plain Python (D37, no pandas)
- [x] Normalise dates to ISO 8601 and amounts to `Decimal`; detect currency from symbols and codes
- [x] Unit tests with the fake LLM client, including a response that breaks the schema

Exit test: extraction on the synthetic fixtures returns schema-valid JSON, and missing fields come back as `null`.

**Exit test passed on 4 Nov 2026** with the fake model (CI run 12, all jobs green). The live Gemini API is proven only once the manual "Gemini smoke test" workflow has run.

---

## Phase 3: Validation and cross-verification (5 Nov)

Goal: the system checks every invoice like an auditor and flags what a human must review.

Validation rules (all in plain Python with `Decimal` and a configurable tolerance):

- [x] `R01` required field missing (invoice number, date, supplier, total); customer and tax only warn (D41)
- [x] `R02` value cannot be parsed or is negative where it must not be
- [x] `R03` sum of line item amounts does not equal subtotal
- [x] `R04` line item quantity times unit price does not equal its amount
- [x] `R05` subtotal plus tax does not equal total
- [x] `R06` duplicate invoice: same normalised supplier and invoice number already stored
- [x] `R07` possible duplicate: same supplier, date and total under a different number
- [x] `R08` date is in the future or unreasonably old
- [x] `R09` field confidence below threshold
- [x] `R10` evidence not found in the source text
- [x] `R11` currency missing or mixed within one invoice
- [x] Review status: any error-level issue sets the invoice to `needs_review`

Cross-verification (from the scenario, beyond the seven tasks):

- [x] Reconciliation service that compares two documents (PDF with PDF, or PDF with Excel)
- [x] Match by normalised invoice number, then fall back to supplier plus date plus total
- [x] Report matched, mismatched (with the differing fields), only in A, only in B

- [x] Unit tests for every rule and for reconciliation, using planted errors

Exit test: every planted error in the fixtures is caught by the right rule.

**Exit test passed on 4 Nov 2026** (CI run 14, all jobs green). Each planted error gives exactly its rule, and clean invoices give no issues.

---

## Phase 4: Backend API, job queue and search (6 Nov)

Goal: the full pipeline runs in the background behind a documented REST API.

Job queue:

- [x] `jobs` table and a worker loop that claims one job at a time with `FOR UPDATE SKIP LOCKED`
- [x] Heartbeat while running; on worker start, re-queue jobs whose heartbeat is stale
- [x] Retry with backoff up to `max_attempts`, then status `failed` with the last error
- [x] A `processing_events` row for every state change

Endpoints (all under `/api`, JWT bearer auth except `health` and `auth/login`):

- [x] `POST /auth/login` for the single demo account defined in environment variables
- [x] `POST /documents` multipart upload of several files, returns `202` with document and job IDs
- [x] `GET /documents` list with status filter and pagination
- [x] `GET /documents/{id}` metadata, status and processing history
- [x] `GET /documents/{id}/results` invoices, line items and validation issues
- [x] `GET /jobs/{id}` job status and progress (pages done out of total)
- [x] `POST /documents/{id}/reprocess` and `POST /jobs/{id}/retry` for failed jobs
- [x] `PATCH /invoices/{id}` manual correction: writes `corrections` rows, re-runs validation, updates search fields
- [x] `GET /review-queue` invoices with status `needs_review`
- [x] `GET /search` keyword mode (full-text plus filters for supplier, date range, amount range, currency, status) and semantic mode (pgvector similarity on invoice embeddings)
- [x] `POST /reconcile` compares two documents and stores the result
- [x] Rate limits on login and upload, CORS restricted to the frontend origin
- [x] Integration tests for every endpoint, including auth failures and a failed job that is retried

Exit test: a mixed batch uploaded to the live Render service is processed in the background and its results are searchable by keyword and by meaning.

**Checklist done on 4 Nov 2026** (CI run 19, all jobs green; the Docker job uploads a CSV through the API, waits for the worker and finds it by search). The exit test itself needs the branch on `main` and a live run on Render; not done yet.

---

## Phase 5: Frontend (6 to 7 Nov)

Goal: a simple, clean interface that covers every user action in the brief.

- [x] Login page
- [x] Upload page: several files at once, drag and drop, per-file status
- [x] Documents list: live progress by polling job status
- [x] Document detail: extracted fields beside the source text, confidence shown per field, validation issues, processing history
- [x] Inline correction of fields, saved through `PATCH /invoices/{id}`
- [x] Review queue page
- [x] Search page: keyword or semantic toggle, filters
- [x] Reconcile page: choose two documents, see the comparison
- [x] Clear states for loading, empty, error and a sleeping backend (cold start message)
- [x] Usable on a phone screen, since the walkthrough is recorded on a phone
- [x] Redesign after Sowan's review (D55): one Home screen, upload on pick, live processing view on every screen, one-tap Approve, bottom tab bar

Exit test: every action in the brief works end to end on the live Vercel URL.

**Checklist done on 4 Nov 2026** (CI run 21 green; a Chromium walk-through at iPhone size covered every action against the real API and worker with the fake model). The exit test on the live Vercel URL waits for the merge to `main`.

---

## Phase 6: Testing and evaluation (dataset from 4 Nov, run on 7 Nov)

Goal: real, measured numbers.

Labelled dataset (`eval/data/`, ground truth JSON beside each file):

- [x] Synthetic invoices from three or four different layouts, with known values
- [x] Planted cases: missing tax, missing customer, wrong totals, wrong line sums, duplicates, several currencies
- [x] Scanned versions: the same invoices rendered to images and degraded (blur, small rotation, noise, JPEG compression)
- [x] One long multi-invoice PDF for segmentation and timing (`long_statement.pdf`: 30 invoices on 37 pages, every fourth over two pages)
- [x] Excel workbook with two sheets, plus a CSV export, matching some PDF invoices for reconciliation
- [x] Broken files: truncated PDF, empty file, wrong extension, encrypted PDF
- [ ] Optional: a few real public invoice or receipt samples, with source and licence recorded

Metrics in `eval/run_eval.py`, results in `eval/reports/` and `docs/EVALUATION.md`:

- [x] Field-level accuracy per field, after normalisation
- [x] Line item precision, recall and F1
- [x] Document success rate and failure rate, with failures grouped by cause
- [x] Processing time per page and per document (mean and 95th percentile), split by digital, OCR and vision paths
- [x] Validation detection rate on planted errors, and the false flag rate on clean invoices
- [x] Tokens per document from the call logs, with an indicative cost labelled as indicative (tokens measured; cost given as tokens times the current price, because the model prices were not confirmed)
- [x] Evaluation workflow in GitHub Actions (manual trigger) using the `GEMINI_API_KEY` secret (manual, or when `eval/eval-request.txt` changes)
- [x] Test results report from CI saved in `docs/` (`docs/TEST_REPORT.md`)

Exit test: `docs/EVALUATION.md` reports every metric from a real run, including the weak results.

**Exit test passed on 4 Nov 2026** with evaluation run 4 (real Gemini, 36 files, 87 invoices). The report includes the weak spots and what runs 1 to 3 found. The optional real samples were not added.

---

## Phase 7: Documentation, walkthrough and submission (7 Nov)

- [x] `README.md`: what it is, live links, one-command local setup, environment variables, how to run tests and evaluation, known limitations
- [x] `docs/ARCHITECTURE.md` with a Mermaid architecture diagram and the data flow
- [x] `docs/SCHEMA.md` with a Mermaid ER diagram
- [x] `docs/SECURITY.md`: what is protected and what production would add
- [x] `docs/AI_USAGE.md`: tools used, prompts, what was AI-generated, how it was verified
- [x] Design decisions section in the README, drawn from `DECISIONS.md`
- [ ] Walkthrough video (3 to 5 minutes, phone screen recording): mixed upload, progress, results, a validation flag, a correction, keyword and semantic search, reconciliation, a failed file and its retry, API docs, CI, evaluation report
- [ ] Final secret scan of the full Git history
- [ ] Repository access for reviewers decided (invite them, or make it public after the scan)
- [ ] Reply All to the Care Guide email with the repo link, live links, video link, CV and portfolio

Exit test: a stranger can follow the README and reach a working system.
