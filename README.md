# DocIntel

DocIntel reads invoices and receipts from PDFs, scans, phone photos, TIFF images, Excel workbooks and CSV files. It extracts the invoice fields with Gemini, checks every number in Python, sends doubtful records to a person, cross-checks one document against another, and makes everything searchable by keyword and by meaning.

I built it for the AI Engineer assessment at Care Guide. The brief is in [docs/BRIEF.md](docs/BRIEF.md).

- Web app: https://docintel-tan-two.vercel.app (the login is in the submission email)
- API docs: https://docintel-api-y25b.onrender.com/api/docs
- Health: https://docintel-api-y25b.onrender.com/api/health (database and file storage)
- Walkthrough video: link added before submission

The backend runs on Render's free plan. It sleeps when idle, so the first request can take up to a minute.

## The brief, task by task

| Task | What is built | Where |
|---|---|---|
| 1. Document processing | Accepts PDF, JPG, PNG, TIFF, XLSX, XLS and CSV, checked by their bytes, not their names. Digital PDF text comes from PyMuPDF, page by page. Scans and photos are cleaned with OpenCV and read by Tesseract; weak pages go to Gemini vision. Every sheet of a workbook is read, with header detection and merged cells. A broken file fails alone with a code such as `CORRUPTED_FILE` or `ENCRYPTED_PDF`. | `backend/app/ingest` |
| 2. AI extraction | Invoice number, date, supplier, customer, subtotal, tax, total, currency and line items, as JSON validated by Pydantic. The model copies each value as printed, with a confidence and the text it came from. A missing value stays empty. Code checks that the evidence appears in the source. | `backend/app/extract`, prompts in `prompts.py` |
| 3. Validation | Eleven rules in `Decimal` arithmetic: missing fields, bad numbers, line sums, quantity times price, subtotal plus tax against total, duplicates (with fuzzy supplier names), dates, low confidence, unproven values, mixed currencies. An error sends the invoice to the review queue. | `backend/app/validate` |
| 4. Backend API | REST endpoints for upload, status, results, search, corrections, reprocessing of failed jobs, reconciliation, export and stats. OCR and model calls run in a background worker. | `backend/app/api`, [API docs](https://docintel-api-y25b.onrender.com/api/docs) |
| 5. Database and search | PostgreSQL holds documents, page text, invoices, line items, validation issues, corrections, jobs and the processing history. Search uses full text with filters, vector similarity with pgvector, or both merged. | [docs/SCHEMA.md](docs/SCHEMA.md), `backend/app/search` |
| 6. Frontend | Next.js. Upload many files at once, watch each move through its steps, inspect fields beside the source text, review and correct issues, search, and compare two documents. | `frontend/` |
| 7. Testing and evaluation | 412 backend tests in CI on Postgres with Tesseract, plus an evaluation on a labelled dataset with the real Gemini models. | [docs/TEST_REPORT.md](docs/TEST_REPORT.md), [docs/EVALUATION.md](docs/EVALUATION.md) |
| Cross-verification | PDF against PDF, or PDF against Excel: matched invoices, mismatched fields, and invoices found on one side only. | `backend/app/validate/reconcile.py`, Compare page |

The deliverables:

1. Source code: this repository.
2. README and setup: this file, from [Run it locally](#run-it-locally).
3. Architecture diagram and database schema: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SCHEMA.md](docs/SCHEMA.md).
4. Working backend API and frontend: the links above.
5. PDF, image, Excel and CSV pipelines: `backend/app/ingest`.
6. Automated tests and results: `backend/tests`, [docs/TEST_REPORT.md](docs/TEST_REPORT.md).
7. Evaluation report with measured metrics: [docs/EVALUATION.md](docs/EVALUATION.md).
8. Walkthrough video: linked above.
9. AI prompts and disclosure: [docs/AI_USAGE.md](docs/AI_USAGE.md), and every runtime prompt in `backend/app/extract/prompts.py`.

## How it works

```mermaid
flowchart LR
    web[Next.js on Vercel] -- "HTTPS + JWT" --> api[FastAPI API]
    subgraph Render["Render, one container"]
        api
        worker[Worker]
    end
    api --> db[(Supabase Postgres<br/>pgvector, pg_trgm, job queue)]
    worker --> db
    api --> files[(Private storage bucket)]
    worker --> files
    worker --> gemini[Gemini: text, vision, embeddings]
```

An upload is checked, stored in a private bucket under a random key, and queued. The API answers at once. A worker claims the job from a PostgreSQL table with `FOR UPDATE SKIP LOCKED` and reads the file. It sends the text to Gemini in windows of eight pages, so an invoice that crosses a page edge stays whole. Python then parses the values, runs the rules and indexes the invoice for search. Every step writes a row to the processing history, which the web app shows live.

The model only reads. All arithmetic, duplicate checks and reconciliation run in Python. Document text sits between fixed markers in the prompt, the model is told to treat it as data, and it gets no tools. One test invoice tells the model to change the total; the system still reads the printed value.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Results

Evaluation run 5 used the real Gemini models on 44 synthetic files with 91 labelled invoices. All eight fields were right on all 91 invoices, and line items matched 224 of 224. Every planted error was caught (12 of 12), with 1 false flag in 80 clean invoices. All 9 broken files got the right error code, all 4 files that are not invoices produced no invoice, and no document failed. Run 6 repeated these results. At paid Gemini prices an invoice costs about $0.0015.

The data is synthetic and cleaner than real invoices, so real accuracy will be lower. Run 7 adds nine phone photos at three levels of difficulty, scored apart from the main set. [docs/EVALUATION.md](docs/EVALUATION.md) has the method, every number, and the weak spots.

## Speed, scale, reliability and security

Speed. Reading a digital page takes about 3 ms. Most of a document's time is waiting for the model: on the free tier, calls are paced to 12 a minute to stay under Google's quota, so a digital PDF took 23 seconds on average in run 5. Spreadsheets usually need no model call and finished in about 2 seconds. On a paid tier, two settings (`LLM_CALLS_PER_MINUTE`, `LLM_MAX_CONCURRENCY`) raise the limit, and the windows of a long PDF run in parallel.

Scale. The brief mentions PDFs of about 1,000 pages. A 1,000-page digital PDF reads in 2.6 seconds with flat memory (160 MB peak), because pages stream in batches. It needs 143 model calls, about 12 minutes on the free tier. On the real queue, with a stand-in model that waits 2 seconds a call, 1, 2 and 4 workers drained the same batch at 1.0x, 2.0x and 3.8x the speed.

Reliability. Jobs live in the database, so they survive a restart. A worker sends a heartbeat, and a job left by a stopped worker is picked up again. Network and quota errors retry with backoff. A failing model falls back to a second one, and a weak scan falls back from vision to the text model to the OCR text. A broken file fails alone and never blocks the batch. `/api/health` checks the database and file storage.

Security. Secrets live only in the Render, Vercel and GitHub settings, and gitleaks scans the full Git history on every push. Uploads are checked by their bytes and limited in size and pages. Files sit in a private bucket. Every route except login and health needs a token, login and upload are rate-limited, and CORS allows only the web app. Logs hold IDs and timings, never document text. [docs/SECURITY.md](docs/SECURITY.md) lists what a production deployment would add.

## Where the build differs from the suggested stack

The brief suggests Node.js or NestJS, Redis with BullMQ, and a vector database, and allows alternatives with reasons.

| Suggested | Used | Why |
|---|---|---|
| Node.js or NestJS | Python and FastAPI | The OCR, PDF and spreadsheet libraries are Python. One language means one deployment and no network hop between API and worker (D01). |
| Redis with BullMQ | A job table in PostgreSQL | Jobs commit in the same transaction as the data they change and survive a restart, with no extra service to run (D02). |
| A separate vector database | pgvector in PostgreSQL | Vectors sit beside the invoices, so one query can filter by supplier, date and amount and rank by meaning (D05). |
| pandas | openpyxl and xlrd, rows converted in plain Python | The readers already turn every cell into text. pandas would add about 60 MB to the image and more memory on a 512 MB instance, for no gain (D37). |

Every design choice, 71 in all, is in [DECISIONS.md](DECISIONS.md) with the alternatives, the reason and the trade-off.

## Run it locally

You need Docker with Compose v2.

```bash
docker compose up --build
```

Open http://localhost:3000 and sign in as `reviewer` with the password `docintel-demo` (local only). Spreadsheets and CSV files work with no keys. PDFs and images need Gemini: copy `.env.example` to `.env`, set `GEMINI_API_KEY`, and keep the model names. Never commit `.env`. The API docs are at http://localhost:8000/api/docs.

## Environment variables

Every setting is in [.env.example](.env.example) with a comment. The main ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection (the Supabase session pooler string on Render) |
| `STORAGE_BACKEND` | `supabase` in production, `local` for compose and tests |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | File storage; the key is an `sb_secret_` key, used by the backend only |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_VISION_MODEL`, `GEMINI_EMBED_MODEL`, `EMBED_DIM` | The models |
| `JWT_SECRET`, `DEMO_USERNAME`, `DEMO_PASSWORD` | The demo login |
| `CORS_ORIGINS` | The web app's address |
| `MAX_FILE_MB`, `MAX_FILES_PER_BATCH`, `MAX_PDF_PAGES` | Upload limits (50 MB, 20 files, 1,500 pages) |
| `OCR_CONFIDENCE_THRESHOLD`, `FIELD_CONFIDENCE_THRESHOLD`, `MONEY_TOLERANCE` | When a page goes to vision, when a field needs review, and the rounding tolerance |
| `LLM_CALLS_PER_MINUTE`, `LLM_MAX_CONCURRENCY` | Model call pacing |

## Tests and evaluation

```bash
cd backend
pip install -r requirements-dev.txt
ruff check . ../eval && ruff format --check . ../eval
pytest
```

Integration tests need a throwaway Postgres with pgvector whose database name contains `test`. Without it they skip.

```bash
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/docintel_test pytest
```

The frontend:

```bash
cd frontend
npm ci
npm run lint && npm run typecheck && npm run build
```

The evaluation needs a throwaway database and a Gemini key. `--fake` checks the scoring without a key, and its accuracy numbers mean nothing.

```bash
cd backend
PYTHONPATH=.:../eval/generate python ../eval/run_eval.py --scale 2 --photos 9
```

CI runs ruff, the backend tests, the frontend build, gitleaks, and a Docker Compose test that uploads a file and finds it by search. Two more workflows use the real Gemini key: "Gemini smoke test" and "Evaluation".

## Known limitations

- The invoices and photos are synthetic. They have no stamps, folds or handwriting, so the accuracy figures are likely optimistic. No real invoices were added, because of licences and personal data.
- The free Render instance sleeps and has 512 MB of memory for the API and the worker together. Large scanned files process slowly.
- The vision model `gemini-3.8-flash` was overloaded in every test run. Weak scans then go to the text model, which still reads them, after a delay.
- Uploading the same invoices twice on purpose, for reconciliation, triggers the duplicate rule (D50).
- Reconciliation compares invoice-level fields, not line items (D43).
- There is one demo account, rate limits are kept in memory, and a token cannot be revoked before it expires (D46).

## Repository

| Path | Holds |
|---|---|
| `backend/app/ingest` | File detection, PDF, OCR, image and spreadsheet readers, upload handling |
| `backend/app/extract` | Gemini client, prompts, schemas, page windows, parsing, evidence checks |
| `backend/app/validate` | Rules R01 to R11, duplicates, reconciliation |
| `backend/app/search` | Full-text and vector search |
| `backend/app/worker` | Job queue, pipeline, worker process |
| `backend/app/api` | REST API |
| `frontend/` | Next.js web app |
| `eval/` | Dataset generator, evaluation runner, load test, Gemini smoke test |
| `docs/` | Brief, architecture, schema, security, evaluation, test report, walkthrough, AI usage |

## How it was built

I made the architecture and scope decisions, and Claude Code wrote most of the code under them, one phase at a time. A phase closed only when its tests passed in CI. One bug got past CI anyway: the first live upload failed because the fake storage service in the tests accepted a request the real one refuses. The fake now copies the real service's rules, and the health check tests storage on the live site (D32). The prompts, the division of work and how each part was checked are in [docs/AI_USAGE.md](docs/AI_USAGE.md).
