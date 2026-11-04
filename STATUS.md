# STATUS.md

Current state of DocIntel. Update this file at the end of every session. Newest entry at the top of the log.

## Now

**Phase:** 1 and 2 done on 4 Nov 2026 (Phase 2 with the fake model; live API pending the smoke test). Phase 3 (validation) built on 4 Nov, waiting on CI. Next: Phase 4 (API, job queue, search).
**Deadline:** 8 November 2026, 03:39 Dhaka. Target submission 7 November 2026, 22:00 Dhaka.

**Live:**

- Web app: https://docintel-tan-two.vercel.app (Vercel project `docintel`)
- API: https://docintel-api-y25b.onrender.com (Render service `docintel-api`, Singapore, free plan). Docs at `/api/docs`, health at `/api/health`.
- Render and Vercel deploy automatically from `main`. Work happens on the session branch; merging into `main` deploys it.

**Supabase (set up by Sowan):** project created, `vector` and `pg_trgm` enabled in the `extensions` schema (on the search_path), private bucket `documents` with a 50 MB limit, Data API disabled. The backend uses SQLAlchemy over the pooler for the database and the Storage API only for files (D17). Code never creates buckets.

**Gemini models (confirmed by Sowan, 4 Nov):** `gemini-3.5-flash-lite` for text, `gemini-3.8-flash` for vision, `gemini-embedding-2` with `output_dimensionality=768`. The embedding model has no `task_type`: queries use the prefix `task: search result | query: ` and documents use `title: {title} | text: ` (D31). Phase 2 and Phase 4 must follow this.

**Supabase key (confirmed by Sowan, 4 Nov):** `SUPABASE_SERVICE_ROLE_KEY` holds a new-style `sb_secret_...` key. The Storage client sends it only in the `apikey` header, never as a Bearer token (D32).

**Next:**

1. Sowan: run the "Gemini smoke test" workflow once (GitHub, Actions tab, Gemini smoke test, Run workflow). It calls the real API on 5 synthetic files and prints fields correct and tokens used. Nothing has called the live Gemini API yet, so this is the first proof that the schema and prompts work. Paste the last 15 lines of the log into the next session.
2. Claude Code ticks Phase 3 once CI is green, then starts Phase 4.
3. Sowan: merge the session branch into `main` when ready.

**Blockers:** None.

**Note:** Render's free instance hours are shared across the workspace with BahasaBot and grab-realtime-demo. Idle services sleep and use no hours, but busy demos elsewhere eat into the same allowance during the review period.

**Open questions:**

1. Repository access at submission: invite the reviewers, or make the repo public after a full secret scan.
2. Whether a few real public invoice samples can be added to the evaluation set.

## Session log

### 4 Nov 2026, Phase 3 build (Claude Code)

Built `app/validate`: rules R01 to R11 as small pure functions with `Decimal` and the money tolerance, duplicate rules R06 and R07 on Postgres with `pg_trgm` similarity, a service that stores issues and sets `needs_review` on any error, and reconciliation (number first, then supplier, date and total) stored in `reconciliations`. The generator gained planted cases for R04, R08, R06 and R07, and a PDF and workbook pair for reconciliation. They are added at the end of the build, so the existing fixtures did not change. Decisions D41 to D43.

Tested in the sandbox: ruff clean, 300 tests pass (40 new), coverage 96%, `alembic check` clean. Exit test: 15 digital PDFs go through ingest, extraction with the fake model and validation. Every planted error gives exactly its rule (R05, R03, R04, R01 warnings for missing tax and customer, R08, R06, R07), and the clean invoices give no issues at all. The reconciliation of the PDF against the workbook finds the expected matched, mismatched, only-in-A and only-in-B invoices.

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
