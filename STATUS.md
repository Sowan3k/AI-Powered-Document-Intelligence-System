# STATUS.md

Current state of DocIntel. Update this file at the end of every session. Newest entry at the top of the log.

## Now

**Phase:** 1 and 2 done on 4 Nov 2026 (Phase 2 with the fake model; live API pending the smoke test). Phase 3 (validation) done on 4 Nov (CI run 14). Phase 4 (API, job queue, search) checklist done on 4 Nov (CI run 19); its exit test waits for the merge to `main`. Phase 5 (frontend) checklist done on 4 Nov (CI run 21). Exit tests for Phases 4 and 5 need the merge to `main`. Phase 6 (evaluation): runner and workflow built, first real run started.
**Deadline:** 8 November 2026, 03:39 Dhaka. Target submission 7 November 2026, 22:00 Dhaka.

**Live:**

- Web app: https://docintel-tan-two.vercel.app (Vercel project `docintel`)
- API: https://docintel-api-y25b.onrender.com (Render service `docintel-api`, Singapore, free plan). Docs at `/api/docs`, health at `/api/health`.
- Render and Vercel deploy automatically from `main`. Work happens on the session branch; merging into `main` deploys it.

**Supabase (set up by Sowan):** project created, `vector` and `pg_trgm` enabled in the `extensions` schema (on the search_path), private bucket `documents` with a 50 MB limit, Data API disabled. The backend uses SQLAlchemy over the pooler for the database and the Storage API only for files (D17). Code never creates buckets.

**Gemini models (confirmed by Sowan, 4 Nov):** `gemini-3.5-flash-lite` for text, `gemini-3.8-flash` for vision, `gemini-embedding-2` with `output_dimensionality=768`. The embedding model has no `task_type`: queries use the prefix `task: search result | query: ` and documents use `title: {title} | text: ` (D31). Phase 2 and Phase 4 must follow this.

**Supabase key (confirmed by Sowan, 4 Nov):** `SUPABASE_SERVICE_ROLE_KEY` holds a new-style `sb_secret_...` key. The Storage client sends it only in the `apikey` header, never as a Bearer token (D32).

**Next:**

1. Sowan: decide on the vision model. In two smoke runs about 10 minutes apart, `gemini-3.8-flash` answered 503 (overloaded) on every try, and the fallback to `gemini-3.5-flash-lite` read both scanned pages correctly. Each weak page waits about 2.5 minutes on the busy model first. Option: set `GEMINI_VISION_MODEL=gemini-3.5-flash-lite` in Render (and `render.yaml`) until Flash recovers. It is a config change, not a code change.
2. Phase 4 exit test: after the merge, upload a mixed batch on the live site and search it. Claude Code can run it once the backend is live.
3. Sowan: merge the session branch into `main`, then in Render check that `DEMO_PASSWORD` is set (Render generates `JWT_SECRET` itself). Then log in through `/api/docs` with user `reviewer`.
4. After the merge: check the live site on a phone (sign in, upload, review, search, reconcile).
5. Claude Code reads the first real evaluation run and writes `docs/EVALUATION.md` from it.

**Blockers:** None.

**Note:** Render's free instance hours are shared across the workspace with BahasaBot and grab-realtime-demo. Idle services sleep and use no hours, but busy demos elsewhere eat into the same allowance during the review period.

**Open questions:**

1. Repository access at submission: invite the reviewers, or make the repo public after a full secret scan.
2. Whether a few real public invoice samples can be added to the evaluation set.

## Session log

### 4 Nov 2026, Phase 6 start (Claude Code)

CI run 21: all four jobs green on the Phase 5 commit. Phase 5 checklist ticked.

Built `eval/run_eval.py` (D51): it generates the dataset, uploads every file, lets the real worker process the queue, and scores field accuracy, line item precision, recall and F1, document outcomes by cause, timing per path (mean and p95), validation detection and false flags, and tokens per document. A dry run with the fake model checked the scoring: every planted error detected, 0 false flags on 34 clean invoices, line items 66 of 66. Three scoring bugs were found and fixed on the way: the loop stopped while retries waited on backoff, spreadsheets were scored on line items they do not contain, and two deliberate reconciliation errors were not labelled as planted. New workflow "Evaluation": runs by hand, or when `eval/eval-request.txt` changes, with the real key.


### 4 Nov 2026, Phase 5 build (Claude Code)

Built the frontend: login, upload (several files, drag and drop, live status per file), documents list (status filter, pages, polls while anything runs), document page (fields beside the source text, confidence and evidence per field, issues, line items, inline correction with "mark as reviewed", correction history, processing history with model calls and tokens, retry and process-again buttons), review queue, search (keyword or by meaning, filters), and reconcile. Loading, empty, error and sleeping-backend states on every page. Decisions D49 and D50.

Tested: lint, typecheck and production build pass. Ran the real API and worker on Postgres with the fake model, and the built web app, then drove it with Chromium at iPhone 13 size. Every step passed: redirect to login, a wrong password, upload of 7 files (5 completed, the empty and the encrypted file failed with their codes), detail page, review queue, correcting the planted wrong total (R05 cleared, status reviewed), keyword search, semantic search, reconciliation (2 matched, 1 mismatched, 1 only in A, 1 only in B), and the failed document's error. The page stayed 390 pixels wide on a 390-pixel screen. The only console error was the 401 from the deliberate wrong password.

Found on the way: quantities showed four decimals ("12.0000"), now trimmed; reconciliation said "pages 2-2", now "page 2". Known limitation recorded as D50: a reconciliation workbook that repeats PDF invoices gets R06 duplicate errors.


### 4 Nov 2026, Phase 4 build and real Gemini check (Claude Code)

Real Gemini, first run (smoke test workflow with Sowan's key): all 4 digital invoices extracted with every field right and no flags, about 650 prompt tokens each. The vision model `gemini-3.8-flash` answered HTTP 503 (overloaded) five times and failed the run. Fix (D44): a weak page now tries the vision model, then the text model, then keeps its Tesseract text. The smoke test now also runs on pushes that change extraction code, since a manual run needs the workflow on `main`. Second run: 48 of 48 fields correct on 6 invoices (4 digital, 2 in the scanned PDF), 5,692 prompt and 4,220 output tokens in total. `gemini-3.8-flash` was still overloaded; `gemini-3.5-flash-lite` read both scanned pages.

Built Phase 4: the job queue (`FOR UPDATE SKIP LOCKED`, heartbeats, stale recovery, backoff, final versus retryable failures), the pipeline (ingest, extract, validate, index), the worker, JWT login, per-IP rate limits, a request size cap, and every endpoint in PHASES.md, plus `GET /reconciliations/{id}`. Search: full text in two forms with weights, and semantic search on pgvector with the D31 query format. Upload code moved to `app/ingest/upload.py`, so the API process never loads OpenCV or PyMuPDF. Spreadsheets now process without a Gemini key, so `docker compose up` works for CSV and Excel with no keys at all. Decisions D44 to D48.

Tested in the sandbox: ruff clean, 337 tests pass (77 new), coverage 95%, `alembic check` clean. Integration tests cover every endpoint, auth failures (missing, bad, forged and expired tokens), rate limits, a job that fails three times on HTTP 503 and then succeeds after `POST /jobs/{id}/retry`, an unreadable file that fails once without retries, two workers getting different jobs under `SKIP LOCKED`, and stale job recovery. Ran the API and worker as real processes on Postgres: upload a CSV, job succeeded, keyword search found it, the worker stopped cleanly on SIGTERM. CI's Docker job now runs the same flow inside the compose stack.

CI run 19: all four jobs green, including the compose upload and search step. Phase 4 checklist ticked; the exit test waits for the live deploy.

Fixed on the way, found by tests: `setweight()` rejected the weight as a bound parameter (now an inline literal), and negated search words slipped through (D47).


### 4 Nov 2026, Phase 3 build (Claude Code)

Built `app/validate`: rules R01 to R11 as small pure functions with `Decimal` and the money tolerance, duplicate rules R06 and R07 on Postgres with `pg_trgm` similarity, a service that stores issues and sets `needs_review` on any error, and reconciliation (number first, then supplier, date and total) stored in `reconciliations`. The generator gained planted cases for R04, R08, R06 and R07, and a PDF and workbook pair for reconciliation. They are added at the end of the build, so the existing fixtures did not change. Decisions D41 to D43.

Tested in the sandbox: ruff clean, 300 tests pass (40 new), coverage 96%, `alembic check` clean. Exit test: 15 digital PDFs go through ingest, extraction with the fake model and validation. Every planted error gives exactly its rule (R05, R03, R04, R01 warnings for missing tax and customer, R08, R06, R07), and the clean invoices give no issues at all. The reconciliation of the PDF against the workbook finds the expected matched, mismatched, only-in-A and only-in-B invoices.

CI run 14: all four jobs green. Phase 3 checklist ticked.

Measured on the way: a one-letter OCR slip in a supplier name scores 0.53, so the supplier similarity default is 0.5, not 0.6 (D42).


### 4 Nov 2026, Phase 2 build (Claude Code)

Built `app/extract`: two-layer schemas (the model returns printed strings with confidence and evidence; code builds typed values), the Gemini client (semaphore, retries on 429, 5xx and timeouts, timeout, token log line per call), the schema-validated call with one retry on invalid output, prompts in `prompts.py`, windowed segmentation with merge rules, the evidence check, parsing of amounts, dates and currencies, spreadsheet column mapping (rules, then the model once per sheet), the vision fallback, and the service that stores invoices, line items and `llm_call` events. Added the manual "Gemini smoke test" workflow. Decisions D36 to D40; D12 updated (no pandas).

Tested in the sandbox: ruff clean, 260 tests pass (113 new), coverage 96%, `alembic check` clean. The exit test uses a fake model that copies values exactly as the generator printed them: all 8 digital PDFs and 4 spreadsheets give the ground truth values, with nulls for the missing tax and customer, and no evidence flags. Other tests cover a reply that breaks the schema (retried once, then `EXTRACTION_FAILED`), an invented value (flagged, confidence halved), a page number outside the window, the vision path on the heavy-noise scan, and network errors that propagate for the job queue.

Fixed on the way: Alembic's logging setup disabled every existing logger when migrations ran in the same process. It now keeps them (`disable_existing_loggers=False`). Production was not affected, since `start.sh` runs Alembic as its own process.

Not tested: any call to the live Gemini API (no key in the sandbox). The smoke test workflow covers it.

CI run 12: all four jobs green, including the Docker build with the Gemini SDK. Phase 2 checklist ticked.


### 4 Nov 2026, Phase 1 build (Claude Code)

Sowan confirmed three things: the Supabase key is an `sb_secret_` key, the `GEMINI_API_KEY` Actions secret exists (ticked in PHASES.md), and the live page shows "API healthy, database connected".

Built Phase 1. `app/ingest`: detection by magic bytes, size, batch and page limits, PDF reader in page batches, scanned page detection, OpenCV cleanup and Tesseract OCR with a confidence per page, JPEG, PNG and multi-page TIFF, `.xlsx`, `.xls` and CSV readers (header detection, merged cells, empty rows, encoding and delimiter), and a service that stores uploads and writes `pages` and `sheets` rows. `app/storage`: one interface with Supabase and local disk backends, closing open question 3. `eval/generate/synth`: seeded generator for 26 fixture files with ground truth and a manifest. Compose now keeps files on an `uploads` volume. CI installs Tesseract and fails if OCR tests would skip. Decisions D32 to D35.

Tested in the sandbox (Tesseract and Postgres with pgvector could be installed this time): ruff clean on backend and generator, 147 tests pass (101 new), coverage 95%, `alembic check` clean. The exit test passes: all 26 fixtures give the expected structure or failure code. OCR confidence on the test scans: 87 to 95 for light noise, about 45 for heavy noise. A test caught a real bug: openpyxl refuses a file with no `.xlsx` extension, which is how the worker saves downloads. Fixed by opening files by handle.

Not tested here: the Docker image build and a real call to Supabase Storage (only a fake transport).

CI run 10: all four jobs green. 147 tests passed, none skipped, with Tesseract required. The Docker job built the image with the new libraries and ran the compose stack. Phase 1 checklist and exit test ticked.


### 4 Nov 2026, Phase 0 closed (Claude Code)

Checked the deploy with the Render, Vercel and Supabase connectors (read only). `main` holds all Phase 0 work. Render: the first deploy failed because `DATABASE_URL` was not set yet, so the app fell back to its localhost default. After Sowan added the values, the live deploy ran migrations, started the worker and served `/api/health` with 200 (database connected). Vercel: production deploy READY from `main`. The sandbox blocks `onrender.com` and `vercel.app`, so the page itself was checked by Sowan, not from here. Ticked the Phase 0 manual items and the exit test; the GitHub Actions secret is still unconfirmed.

Fix from that failed deploy: in production, settings now stop at startup with "DATABASE_URL must be set when APP_ENV=production" (same for `CORS_ORIGINS`) instead of trying localhost. Settings errors never echo input values, so a bad value cannot print the database password into logs. Tested: 46 tests pass; ran `alembic upgrade head` as production without `DATABASE_URL` and got the clear message.

### 4 Nov 2026, Render setup check (Claude Code)

Checked with the Render and Supabase connectors (read only, no secrets touched). No `docintel-api` service exists yet, and `main` holds only the planning files, so the branch must be merged before the Blueprint can create the service. Rewrote the Render step: where each value comes from, the `[YOUR-PASSWORD]` placeholder in the pooler string, the Supabase project URL, and that the Blueprint generates `JWT_SECRET`. Closed the Postgres 17 question.

### 4 Nov 2026, Gemini model config (Claude Code)

Set the confirmed model names in `.env.example` and `render.yaml` (model names are not secrets, so Render no longer asks for them). Recorded D31: Flash-Lite for text extraction, Flash for the vision fallback, `gemini-embedding-2` at 768 dimensions, and the exact query and document prefixes. Tested: unit tests pass, including the check that `.env.example` parses and documents every setting.

### 4 Nov 2026, Supabase rules and pg_trgm (Claude Code)

Recorded Sowan's Supabase setup. Added D17: the Data API is disabled, the backend reaches Postgres only through SQLAlchemy and files only through the Storage API, never `supabase-js` or the table client. The earlier D17 to D28 moved to D18 to D29, and all references in code and docs moved with them. Added D30: `pg_trgm` for fuzzy supplier matching. Migration `0001` (never applied to Supabase yet, since `main` does not contain it) now also runs `CREATE EXTENSION IF NOT EXISTS pg_trgm` and adds a GIN trigram index on `invoices.supplier_norm`. A new unit test fails CI if any Supabase client package appears in the backend or frontend dependencies.

Tested: ruff clean, 40 tests pass (26 unit, 14 integration), including a trigram similarity query and a run where both extensions already exist. Also ran the migration on a local copy of the Supabase layout (extensions in an `extensions` schema on the search_path): it ran, left the extensions where they were, and `alembic check` found no drift.

### 4 Nov 2026, Phase 0 build (Claude Code)

Built the Phase 0 code. Backend: FastAPI app factory, settings from environment (secrets as `SecretStr`), `/api/health/live` and `/api/health`, worker loop with clean shutdown, SQLAlchemy models for all ten tables, hand-written migration `0001`. `start.sh` runs migrations, then the API and the worker, and exits if either dies. Frontend: Next.js 16 page that calls `/api/health` and shows healthy, degraded, unreachable and cold-start states. Added Dockerfiles, `docker-compose.yml`, `render.yaml` and the CI workflow (ruff, migrations, pytest, frontend build, gitleaks, Docker compose smoke test). Added decisions D18 to D29.

Tested in the sandbox:

1. Ruff lint and format: clean.
2. Pytest: 36 passed (24 unit, 12 integration on Postgres with pgvector). Coverage 94%.
3. Migration: upgrade, `alembic check` (no drift from the models), downgrade, upgrade again.
4. Backend container: health OK, clean stop exits 0, a killed worker stops the container, a bad database URL fails the start.
5. Full compose stack (Postgres 17, pgvector 0.8.7): migrations ran, worker started, and Chromium at phone width showed "API healthy, database connected".
6. Frontend: lint, typecheck and production build pass. Degraded and unreachable states checked in Chromium.

Not tested in the sandbox: the Tesseract install step (the sandbox blocks the Debian mirror) and gitleaks (the sandbox blocked downloading the binary). CI covers both.

CI run 1 on commit `0b3bdb3`: all four jobs passed. Backend (ruff, migrations, `alembic check`, 36 tests), frontend (lint, typecheck, build), gitleaks over the full history, and the Docker job (both images built, Tesseract present, compose stack healthy, worker started, web app answering). The seven Claude Code items in the Phase 0 checklist are ticked. The six manual items and the exit test remain.

Fixed during testing: ORM relationships lacked `cascade="all, delete-orphan"`, so deleting a document failed when its invoices were loaded. A test caught it.

### 4 Nov 2026, planning (Claude chat)

Read the brief. Chose the stack and recorded the reasons in `DECISIONS.md` (D01 to D16). Wrote the phase plan. No code yet.
