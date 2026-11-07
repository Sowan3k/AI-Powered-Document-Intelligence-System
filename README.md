# DocIntel

DocIntel reads invoices and receipts from PDFs, scans, phone photos, TIFF images, Excel workbooks and CSV files. It extracts the invoice fields with Gemini, checks every number in Python, sends doubtful records to a person, cross-checks one document against another, and makes everything searchable by keyword and by meaning.

I built it for the AI Engineer assessment at Care Guide. The brief is in [docs/BRIEF.md](docs/BRIEF.md).

- Web app: https://docintel-tan-two.vercel.app (the login is in the submission email)
- API docs: https://docintel-api-y25b.onrender.com/api/docs
- Health: https://docintel-api-y25b.onrender.com/api/health (database and file storage)
- Walkthrough video: https://youtu.be/n9xKvACPR90
- Deliverables report: [read it here](docs/DELIVERABLES.md), or [download the PDF](https://github.com/Sowan3k/AI-Powered-Document-Intelligence-System/raw/main/docs/DocIntel-Deliverables.pdf) (6 pages)

The backend runs on Render's free plan. It sleeps when idle, so the first request can take up to a minute. The web app's opening page starts waking it the moment it loads and shows the real status at the top, with Sign in beside it.

## Deliverables

The brief asks for nine things, submitted within five days. Each one is here. The same list, with the key results of each, diagrams and screenshots, is in the [deliverables report](docs/DELIVERABLES.md). **[Download it as a PDF](https://github.com/Sowan3k/AI-Powered-Document-Intelligence-System/raw/main/docs/DocIntel-Deliverables.pdf).**

| # | Deliverable | Where it is |
|---|---|---|
| 1 | Git repository with the source code | This repository: `backend/` (FastAPI API and worker), `frontend/` (Next.js), `eval/` (dataset and evaluation). Every step is in the Git history. |
| 2 | README and setup instructions | This file. [Installation and setup](#installation-and-setup) gives two ways to run the system: one Docker Compose command, or each part by hand. [Environment variables](#environment-variables) lists every setting, and `.env.example` holds placeholders only. |
| 3 | Architecture diagram and database schema | [How it works](#how-it-works) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) hold the architecture and data flow diagrams. [docs/SCHEMA.md](docs/SCHEMA.md) holds the ER diagram of all ten tables. |
| 4 | Working backend API and frontend | Web app: https://docintel-tan-two.vercel.app. API docs: https://docintel-api-y25b.onrender.com/api/docs. Both deploy from `main`. |
| 5 | PDF, image, Excel and CSV pipelines | `backend/app/ingest`. Digital PDFs through PyMuPDF; scans and photos through OpenCV and Tesseract, with Gemini vision for weak pages and every phone photo; Excel through openpyxl and xlrd; CSV through Python's csv module, which detects the encoding and the delimiter. All four give the same internal structure to the extraction step. |
| 6 | Automated tests and test results | `backend/tests`, with unit tests and integration tests on Postgres. CI runs them on every push. [docs/TEST_REPORT.md](docs/TEST_REPORT.md): 428 passed with 96% line coverage in CI run 84. |
| 7 | Evaluation report with measured metrics | [docs/EVALUATION.md](docs/EVALUATION.md): eight runs with the real Gemini models on a labelled dataset. Accuracy per field, line items, planted errors caught, false flags, broken files, time per document, tokens and cost, and the weak spots. |
| 8 | Recorded walkthrough | https://youtu.be/n9xKvACPR90, recorded on a phone on the live site. The planned script is in [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md). |
| 9 | AI prompts and disclosure | [docs/AI_USAGE.md](docs/AI_USAGE.md): the tools, the main prompts, what AI wrote and how each part was checked. Every prompt the system sends to Gemini is in `backend/app/extract/prompts.py`. |

The brief also asks for smooth performance, high speed, scalability, reliability and strong security. The short version is below; [Speed, scale, reliability and security](#speed-scale-reliability-and-security) has the measurements.

| Quality | What shows it |
|---|---|
| Smooth performance | Uploads return at once and the work runs in the background, with each file's steps shown live. Home holds 60 frames a second with the CPU slowed four times. Long PDFs show their pages as you scroll. |
| High speed | A digital page reads in about 3 ms and a spreadsheet in about 2 seconds. The windows of a long PDF go to the model in parallel. Most of the remaining time is the free tier's limit of 12 model calls a minute, which is a setting. |
| Scalability | A 1,000-page PDF reads in 2.6 seconds with a 160 MB memory peak, because pages stream in batches. The job queue lets workers share the load: 1, 2 and 4 workers ran 1.0x, 2.0x and 3.8x as fast. |
| Reliability | Jobs live in the database and survive a restart. Failed calls retry with backoff, a failing model falls back to a second one, and a broken file fails alone without stopping the batch. A health check covers the database and file storage. |
| Strong security | Secrets live only in the hosting settings, and gitleaks scans the full Git history on every push. Uploads are checked by their bytes. Files sit in a private bucket. Every route except login and health needs a login token, login and upload are rate-limited, and logs never hold document text. See [docs/SECURITY.md](docs/SECURITY.md). |

## Installation and setup

You can run the whole system on your own machine in two ways. Docker is the quick one. Both read spreadsheets and CSV files with no key. PDFs and images need a Gemini API key, free from [Google AI Studio](https://aistudio.google.com/apikey).

### Option 1: Docker (recommended)

You need Git and Docker with Compose v2.

```bash
git clone https://github.com/Sowan3k/AI-Powered-Document-Intelligence-System.git
cd AI-Powered-Document-Intelligence-System
```

Create a file named `.env` in that folder with these four lines, and put your key in the first:

```bash
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_VISION_MODEL=gemini-3.8-flash
GEMINI_EMBED_MODEL=gemini-embedding-2
```

Then start everything:

```bash
docker compose up --build
```

This starts four containers: Postgres with pgvector, the API (it creates the tables first), the background worker and the web app. The first build takes a few minutes.

- Web app: http://localhost:3000. Sign in as `reviewer` with the password `docintel-demo`. This login works on your machine only.
- API docs: http://localhost:8000/api/docs
- Stop with `Ctrl+C`. `docker compose down -v` also deletes the local database and uploaded files.

Do not copy `.env.example` to `.env` for this. It holds placeholders for the hosted setup, and Compose would read its `DEMO_PASSWORD=replace-me` instead of the local password. Git ignores `.env`, so your key never reaches the repository.

### Option 2: Without Docker

You need Python 3.12, Node.js 20.9 or later, PostgreSQL 16 or 17 with the pgvector extension, and Tesseract OCR 5 with English (`apt install tesseract-ocr` on Ubuntu, `brew install tesseract` on macOS). Create an empty database. Its user must be allowed to create the `vector` and `pg_trgm` extensions, or a superuser creates them first.

Backend, in one terminal:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```bash
APP_ENV=development
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/docintel
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=./data/uploads
DEMO_USERNAME=reviewer
DEMO_PASSWORD=choose-a-password
JWT_SECRET=a-long-random-string
CORS_ORIGINS=http://localhost:3000
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_VISION_MODEL=gemini-3.8-flash
GEMINI_EMBED_MODEL=gemini-embedding-2
```

Then create the tables and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --port 8000
```

The worker, in a second terminal (it does the reading, OCR and model calls):

```bash
cd backend
source .venv/bin/activate
python -m app.worker.main
```

The web app, in a third terminal:

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000 and sign in as `reviewer` with the password you chose.

### Check that it works

1. `curl http://localhost:8000/api/health` answers with `"database":"connected"` and `"storage":"ok"`.
2. Make sample invoices to try: with the backend's Python environment active, run `cd eval/generate && python -m synth --out ~/docintel-samples`. It writes about 40 files (digital and scanned PDFs, photos, TIFF, Excel, CSV and some broken files), each with its correct answer in a `.json` file beside it.
3. Sign in and upload a few of them. Each file's steps appear on Home as it is processed, and its invoices appear when it is done.

Every other setting is optional. They are listed in [Environment variables](#environment-variables) and in [.env.example](.env.example).

## Screenshots

Real screenshots of the running app on demo data, not mockups.

### Opening page and sign in

| Opening page | Scrolling down | Sign in |
|---|---|---|
| ![Opening page with the headline "Invoices in. Checked data out." and a "Server ready" status beside Sign in](docs/screenshots/landing.webp) | ![The scroll animation: a phone shows a review screen with 11 checks per invoice, beside "Every number, checked."](docs/screenshots/landing-card.webp) | ![Sign-in page with three checks for server, database and file storage, all green, beside a sample extracted invoice](docs/screenshots/sign-in.webp) |

The opening page wakes the sleeping backend the moment it loads. The sign-in page shows the server, the database and the file storage coming up one by one.

### Home in light and dark

| Light | Dark |
|---|---|
| ![Home in light mode: the upload box, then the invoices that need attention, each with its problem in plain words](docs/screenshots/home.webp) | ![The same Home page in dark mode](docs/screenshots/home-dark.webp) |

The upload box takes PDFs, photos, TIFF, Excel and CSV files in one batch. Below it, each flagged invoice says what is wrong, for example "subtotal plus tax is 418.75, but the total is 428.75", with Fix and Approve beside it.

### One document, and the review queue

| Document | Review |
|---|---|
| ![Document page: each extracted field with its confidence and the quote it came from, and the source text with those quotes highlighted](docs/screenshots/document.webp) | ![Review queue: each invoice with a problem, the rule that flagged it, and buttons to open and fix or approve](docs/screenshots/review.webp) |

Every field shows a confidence score and the exact words it was read from. The source text on the right highlights those words, so a reviewer can check a value without opening the file.

### Search and compare

| Search | Compare |
|---|---|
| ![Search for "Padma" in best-match mode, which combines exact words and meaning, with 14 results](docs/screenshots/search.webp) | ![Compare: a supplier statement PDF against an Excel register, with a bar and four counts, and one pair whose totals differ by 25.00](docs/screenshots/compare.webp) |

Search combines keyword and meaning, with filters for supplier, currency, date, total and review status. Compare checks one document against another. Here a PDF statement and an Excel register share three invoices, and one total differs by 25.00.

### On a phone

| Home | Document | Review | Compare |
|---|---|---|---|
| ![Home on a phone in dark mode, with the tab bar at the bottom](docs/screenshots/phone-home.webp) | ![A document's fields and evidence on a phone](docs/screenshots/phone-document.webp) | ![The review queue on a phone](docs/screenshots/phone-review.webp) | ![The comparison on a phone](docs/screenshots/phone-compare.webp) |

The whole app works on a phone. I built and tested it from one.

## The brief, task by task

| Task | What is built | Where |
|---|---|---|
| 1. Document processing | Accepts PDF, JPG, PNG, TIFF, XLSX, XLS and CSV, checked by their bytes, not their names. Digital PDF text comes from PyMuPDF, page by page. Scans and photos are cleaned with OpenCV and read by Tesseract. Weak scan pages and every phone photo go to Gemini vision. Every sheet of a workbook is read, with header detection and merged cells. A broken file fails alone with a code such as `CORRUPTED_FILE` or `ENCRYPTED_PDF`. | `backend/app/ingest` |
| 2. AI extraction | Invoice number, date, supplier, customer, subtotal, tax, total, currency and line items, as JSON validated by Pydantic. The model copies each value as printed, with a confidence and the text it came from. A missing value stays empty. Code checks that the evidence appears in the source. | `backend/app/extract`, prompts in `prompts.py` |
| 3. Validation | Eleven rules in `Decimal` arithmetic: missing fields, bad numbers, line sums, quantity times price, subtotal plus tax against total, duplicates (with fuzzy supplier names), dates, low confidence, unproven values, mixed currencies. An error sends the invoice to the review queue. | `backend/app/validate` |
| 4. Backend API | REST endpoints for upload, status, results, search, corrections, reprocessing of failed jobs, reconciliation, export and stats. OCR and model calls run in a background worker. | `backend/app/api`, [API docs](https://docintel-api-y25b.onrender.com/api/docs) |
| 5. Database and search | PostgreSQL holds documents, page text, invoices, line items, validation issues, corrections, jobs and the processing history. Search uses full text with filters, vector similarity with pgvector, or both merged. | [docs/SCHEMA.md](docs/SCHEMA.md), `backend/app/search` |
| 6. Frontend | Next.js. Upload many files at once, watch each move through its steps, inspect fields beside the source text, review and correct issues, search, and compare two documents. | `frontend/` |
| 7. Testing and evaluation | 429 backend tests in CI on Postgres with Tesseract, plus an evaluation on a labelled dataset with the real Gemini models. | [docs/TEST_REPORT.md](docs/TEST_REPORT.md), [docs/EVALUATION.md](docs/EVALUATION.md) |
| Cross-verification | PDF against PDF, or PDF against Excel: matched invoices, mismatched fields, and invoices found on one side only. The Compare page suggests pairs that share invoices. | `backend/app/validate/reconcile.py`, Compare page |

## How it works

![System overview: the Next.js web app on Vercel calls the FastAPI API on Render; the API and worker share one container and use Supabase Postgres, a private storage bucket and Gemini](docs/diagrams/system-overview.png)

An upload is checked, stored in a private bucket under a random key, and queued. The API answers at once. A worker claims the job from a PostgreSQL table with `FOR UPDATE SKIP LOCKED` and reads the file. It sends the text to Gemini in windows of eight pages, so an invoice that crosses a page edge stays whole. Python then parses the values, runs the rules and indexes the invoice for search. Every step writes a row to the processing history, which the web app shows live.

The model only reads. All arithmetic, duplicate checks and reconciliation run in Python. Document text sits between fixed markers in the prompt, the model is told to treat it as data, and it gets no tools. One test invoice tells the model to change the total; the system still reads the printed value.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Results

Evaluation run 5 used the real Gemini models on 44 synthetic files with 91 labelled invoices. All eight fields were right on all 91 invoices, and line items matched 224 of 224. Every planted error was caught (12 of 12), with 1 false flag in 80 clean invoices. All 9 broken files got the right error code, all 4 files that are not invoices produced no invoice, and no document failed. Run 6 repeated these results. At paid Gemini prices an invoice costs about $0.0015.

The data is synthetic and cleaner than real invoices, so real accuracy will be lower. Run 7 showed how much. It read nine phone photos at three levels of difficulty and got 77.8% of their fields right. Every error came from photos that Tesseract read with high confidence, which kept them away from the vision model: "Ltd" read as "Lid", "Valley" as "Vattey". Run 8 sends every phone photo to the vision model (D82). Photo fields rose to 87.5% right, with mild and medium photos at 100%. The one miss was a hard photo whose invoice number the vision model misread. The main set stayed at 100% on every field and every planted error, but Gemini overload errors used up the 45-minute budget before 6 of its 45 files ran. [docs/EVALUATION.md](docs/EVALUATION.md) has the method, every number, and the weak spots.

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

Every design choice, 85 in all, is in [DECISIONS.md](DECISIONS.md) with the alternatives, the reason and the trade-off.

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
| `VISION_FOR_PHOTOS` | Send every JPEG and PNG photo to vision, whatever Tesseract's confidence (on by default) |
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
- Every phone photo now goes to the vision model (D82). That costs one vision call per page and adds time. Hard photos stay the weak spot: in run 8, one of three had its invoice number misread.
- The free Render instance sleeps and has 512 MB of memory for the API and the worker together. Large scanned files process slowly.
- The vision model `gemini-3.8-flash` returned overload errors in every test run. The client retries with backoff. A page whose vision call still fails keeps its OCR text and goes to the text model. In run 8 the retries ran the evaluation past its 45-minute budget.
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
| `docs/` | Deliverables report (also as a PDF), brief, architecture, schema, security, evaluation, test report, walkthrough, AI usage |

## How it was built

I made the architecture and scope decisions, and Claude Code wrote most of the code under them, one phase at a time. A phase closed only when its tests passed in CI. One bug got past CI anyway: the first live upload failed because the fake storage service in the tests accepted a request the real one refuses. The fake now copies the real service's rules, and the health check tests storage on the live site (D32). The prompts, the division of work and how each part was checked are in [docs/AI_USAGE.md](docs/AI_USAGE.md).
