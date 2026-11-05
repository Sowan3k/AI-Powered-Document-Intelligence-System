# DECISIONS.md

Every design choice in DocIntel, with the reason behind it. Each entry follows the same format: the decision, the alternatives considered, why this choice, what it costs, and a one-line answer for an interview. Add new entries at the end. Do not delete old ones; mark them `Superseded by Dxx` if they change.

---

## D01: Python with FastAPI for the backend, not Node.js with NestJS

**Alternatives:** NestJS (suggested in the brief), Django.

**Why:** Every heavy part of the task lives in Python: PyMuPDF for PDFs, Tesseract bindings, OpenCV, pandas, openpyxl and the Gemini SDK. A Node.js API would still need a Python service for processing, which means two languages, two deployments and a network hop between them. FastAPI uses Pydantic, so the same models validate API input and LLM output. It also generates interactive API documentation, which reviewers can use directly. I built BahasaBot on FastAPI, so the five days went into the problem, not into learning a framework.

**Trade-off:** The brief lists NestJS and BullMQ. A reviewer who expects Node.js needs this explanation.

**In one sentence:** The processing ecosystem is Python, so one Python service is simpler and has fewer failure points than a Node.js API calling a Python worker.

---

## D02: A PostgreSQL job table as the queue, not Redis with BullMQ or Celery

**Alternatives:** Redis with Celery or RQ, BullMQ (Node.js only), a managed cloud queue.

**Why:** The free Render instance can restart at any time. A job that lives in the same database as the document survives a restart, and its state is always consistent with the data it changes. Workers claim jobs with `SELECT ... FOR UPDATE SKIP LOCKED`, so two workers never take the same job. A heartbeat column lets a new worker detect and re-queue jobs left behind by a crashed one. That same mechanism gives the brief's "failed-job reprocessing" requirement directly. It also removes one service to host, secure and monitor.

**Trade-off:** Postgres queues handle far less throughput than Redis. At thousands of documents per hour with many workers, the polling load on the database would grow. Production at that scale would move to a dedicated queue with separate worker machines. The job interface is isolated in `backend/app/worker/` so that swap stays small.

**In one sentence:** For this scale and free hosting, a durable queue in the same transactional database is more reliable than an extra in-memory service, and the design leaves a clear path to Redis when volume demands it.

---

## D03: The worker runs as a separate process in the same container

**Alternatives:** A Render background worker service (not available on the free plan), a background thread inside the API process.

**Why:** OCR is CPU-heavy. Inside the API process it would block request handling. A separate process keeps the API responsive. Render's free plan offers web services but not background workers, so `start.sh` launches both processes in one container.

**Trade-off:** API and worker share 512 MB RAM and a small CPU share, so processing is slow under load. Production would run workers on their own instances and scale them independently.

**In one sentence:** Separate processes keep the API responsive, and one container keeps it free; production would split them onto separate machines.

---

## D04: Supabase for the database and file storage

**Alternatives:** Render's free Postgres, MongoDB Atlas, Neon.

**Why:** Supabase gives PostgreSQL with pgvector and private file storage in one project. File storage matters because Render's free web services have no persistent disk, so uploaded files saved locally would vanish on restart, and failed jobs could not be reprocessed. Render's free Postgres expires after 30 days, which could fall inside the review period.

**Trade-off:** One more external provider and one more set of credentials to protect. Supabase free projects pause after a period of inactivity.

**In one sentence:** Supabase solves three needs (relational data, vectors and durable file storage) in one place, which free Render alone cannot.

---

## D05: pgvector inside PostgreSQL, not a separate vector database

**Alternatives:** Pinecone, Qdrant, Chroma.

**Why:** Semantic search here runs over thousands of invoices, not hundreds of millions of vectors. Keeping embeddings next to the invoice rows means one query can combine meaning with exact filters (supplier, date range, amount, status). It also means one backup, one access control model and no sync job between two stores.

**Trade-off:** A dedicated vector database scales further and offers more tuning. That becomes worth the extra system only at a much larger corpus.

**In one sentence:** At this scale, vectors beside the relational data give simpler filtering and consistency than a second database.

---

## D06: PostgreSQL rather than MongoDB

**Alternatives:** MongoDB (listed in the brief).

**Why:** The data is relational: a document holds invoices, an invoice holds line items, issues and corrections. Money needs exact decimal types. Duplicate detection needs unique constraints. Full-text search is built in. Flexible per-field metadata (confidence, evidence) fits in JSONB columns, so the schema stays strict where it must be and flexible where it helps.

**Trade-off:** Schema changes need migrations. Alembic handles that.

**In one sentence:** Financial data needs exact numbers, relations and constraints, which PostgreSQL provides natively.

---

## D07: Hybrid OCR: Tesseract first, Gemini vision only for low-confidence pages

**Alternatives:** Tesseract only, PaddleOCR, a vision LLM for every image.

**Why:** Tesseract is free, runs inside the container and handles clean scans well. It reports a confidence score per word, so the system knows when it struggled. Only those pages go to Gemini vision, which reads poor scans far better. PaddleOCR is more accurate than Tesseract but too heavy for a 512 MB instance.

**Trade-off:** Two OCR paths to test. Pages sent to Gemini leave the server and cost API calls. The evaluation report shows how many pages took each path.

**In one sentence:** Cheap local OCR handles most pages, and the expensive model is used only where measured confidence says it is needed.

---

## D08: Gemini as the LLM

**Alternatives:** OpenAI, Anthropic, a local model through Ollama.

**Why:** Gemini supports structured JSON output against a schema, reads images for the OCR fallback, and provides embeddings, so one provider covers extraction, vision and search. Its free tier makes development possible without a budget. I used Gemini in BahasaBot, including quota handling and token logging.

**Trade-off:** Free-tier rate limits slow the evaluation run. Documents are sent to an external provider. The client module isolates the provider, so switching models is a configuration change.

**In one sentence:** One provider covers structured extraction, vision and embeddings, behind a client module that keeps it replaceable.

---

## D09: The LLM extracts; code calculates

**Alternatives:** Ask the LLM to check the totals itself.

**Why:** Language models make arithmetic mistakes and give different answers to the same input. Financial checks must be exact and repeatable. So the model only reads values, and every sum, tax check, duplicate check and reconciliation runs in Python with `Decimal`.

**Trade-off:** More code to write than one clever prompt.

**In one sentence:** The model reads; deterministic code decides whether the numbers are right.

---

## D10: Null with confidence and evidence instead of guessed values

**Alternatives:** Let the model fill every field.

**Why:** In finance a confident wrong number does more damage than a blank. The model returns `null` when unsure, plus a confidence score and the text snippet it used. Code then checks that the invoice number and total really appear in the source text. A value without evidence is flagged for review instead of being trusted.

**Trade-off:** More invoices go to manual review. That is the intended behaviour.

**In one sentence:** Every extracted value must show where it came from, and anything unproven goes to a human.

---

## D11: Large PDFs in page batches, with windowed invoice segmentation

**Alternatives:** Load the whole PDF and send it to the model at once.

**Why:** A 1,000-page PDF does not fit in 512 MB of memory as rendered images, and it does not fit in one model call. PyMuPDF reads pages in batches. Segmentation sends overlapping windows of pages to the model, which returns invoices with page ranges. Invoices that cross a window edge are merged. Progress is reported as pages done out of the total.

**Trade-off:** Window edges need careful merge logic and tests.

**In one sentence:** Streaming pages in batches keeps memory flat, and overlapping windows keep invoices whole.

---

## D12: Spreadsheets mapped by rules first, LLM once per sheet

**Alternatives:** Send every row to the LLM.

**Why:** A spreadsheet is already structured. The only hard part is knowing which column means "total" or "supplier". Known header names are matched by rule. When a column is unclear, the LLM sees only the header row and a few sample rows, once per sheet. pandas then converts every row. A 10,000-row sheet costs one model call, not 10,000.

**Trade-off:** Unusual layouts, such as one invoice spread across several rows, need special handling.

**In one sentence:** Use the model to understand the layout once, then let pandas do the rows.

**Update (D37):** the rows are converted in plain Python, not pandas. The rest of this decision stands.

---

## D13: A synthetic labelled dataset as the core of evaluation

**Alternatives:** Public datasets only, or hand-labelling real invoices.

**Why:** A generated invoice comes with exact ground truth. It also lets me plant specific errors (wrong totals, duplicates, missing fields) to measure whether validation catches them, and to build a long multi-invoice PDF for timing. Degraded image copies test OCR on known content.

**Trade-off:** Synthetic layouts are cleaner than real ones, so results may be optimistic. The report states this, and adds real public samples where licensing and access allow.

**In one sentence:** Synthetic data gives exact answers and controlled errors; the report is honest about its limits.

---

## D14: JWT login for the web interface; the browser calls the API directly

**Alternatives:** No authentication, an API key in the frontend, routing uploads through Next.js server functions.

**Why:** Financial documents need access control even in a demo. A single demo account, configured by environment variables, issues a short-lived JWT. The browser sends files straight to the API, because serverless platforms limit request body size and would block large uploads. CORS allows only the frontend origin.

**Trade-off:** One demo account is not real user management. Production would use the company's single sign-on and per-user roles.

**In one sentence:** Real authentication at demo scale, with a clear path to single sign-on.

---

## D15: Free-tier hosting with stated limits

**Alternatives:** Paid instances.

**Why:** The project has no budget, and the free tiers are enough to show a working system.

**Trade-off:** The Render service sleeps after a period without traffic, so the first request can take close to a minute. It can also restart at any time, which D02 and D04 are designed to survive. The README and the submission email state this.

**In one sentence:** Free hosting is enough to prove the design, and the design already handles its restarts.

---

## D16: Cross-verification added beyond the seven tasks

**Alternatives:** Build only what the task list requires.

**Why:** The scenario names PDF-to-PDF and PDF-to-Excel cross-verification as daily manual work, but none of the seven tasks asks for it. A reconciliation endpoint matches invoices across two documents by invoice number, then by supplier, date and total, and reports matches, mismatched fields and missing records.

**Trade-off:** Time taken from other phases. It is scheduled after validation, so it can be cut if earlier phases run late.

**In one sentence:** It addresses a pain the company described, not only the checklist it wrote.

---

## D17: Supabase Data API disabled; the backend reaches Postgres only through SQLAlchemy

**Alternatives:** `supabase-js` in the frontend with row level security, or the Supabase table client (PostgREST) in the backend.

**Why:** Least privilege. The frontend never talks to Supabase directly (D14), so nothing needs Supabase's auto-generated REST API over the tables. With the Data API turned off, no table can be reached through Supabase's public API, even if a key leaks or a row level security policy is wrong. The backend reaches the database only with SQLAlchemy over the Session pooler string, so every query goes through the same models, transactions and ORM parameters (security rule 6). Files go through the Supabase Storage API, called only by the backend with the service role key. The private bucket `documents` (50 MB file limit) was created in the dashboard; code never creates or changes buckets. A unit test fails CI if `supabase-js`, any `@supabase/` package, or the Python `supabase` or `postgrest` packages appear in the dependencies.

**Trade-off:** No Supabase realtime, auto-generated REST endpoints or browser-side queries. Every new data need is a FastAPI endpoint, and the frontend polls the backend for progress.

**In one sentence:** One door into the database, owned by the backend; Supabase's public Data API stays closed.

---

## D18: Synchronous SQLAlchemy sessions, not async

**Alternatives:** Async SQLAlchemy with `asyncpg` or async psycopg.

**Why:** The API and the worker share the same models and database code. The worker is CPU-bound (OCR, PDF parsing), so async gives it nothing. FastAPI runs plain `def` endpoints in a thread pool, which is enough for a demo-scale API. One session style means one set of helpers and simpler tests.

**Trade-off:** Each in-flight request holds a thread. Under thousands of concurrent requests an async stack would use less memory. That load is far beyond this deployment.

**In one sentence:** The slow work is CPU-bound, so async would add complexity without adding speed.

---

## D19: Embedding size fixed by `EMBED_DIM` when the migration runs

**Alternatives:** Hard-code the dimension in the migration, or use an untyped vector column.

**Why:** Model names and their output sizes are configuration (CLAUDE.md). The first migration reads `EMBED_DIM` and creates `vector(EMBED_DIM)`. It also creates an HNSW index with cosine distance, but only when the size is 2,000 or less, because pgvector cannot index larger `vector` columns with HNSW. Gemini embedding models can return a reduced size, so 768 keeps the index possible and the rows small.

**Trade-off:** Changing `EMBED_DIM` after the first deploy needs a new migration and fresh embeddings. Stored vectors from different models cannot be mixed anyway.

**In one sentence:** The vector size follows configuration, and the index exists whenever pgvector can build it.

---

## D20: Status columns as VARCHAR with CHECK constraints, not native Postgres enums

**Alternatives:** Native `CREATE TYPE ... AS ENUM`, or free text with no constraint.

**Why:** A CHECK constraint still stops bad values at the database. Changing the allowed values is a plain constraint swap in a migration. A native enum needs `ALTER TYPE`, which has transaction limits and cannot remove a value. The Python side uses `StrEnum`, so code gets type safety too.

**Trade-off:** Slightly more storage than a native enum. Irrelevant at this scale.

**In one sentence:** Same protection as an enum, with migrations that stay simple.

---

## D21: UUID keys for rows the API exposes, BIGINT keys for child rows

**Alternatives:** UUIDs everywhere, or integers everywhere.

**Why:** Documents, invoices, jobs and reconciliations appear in URLs. Random UUIDs cannot be guessed or counted. Pages, line items, validation issues, corrections and events are always reached through a parent. A 1,000-page PDF creates 1,000 page rows, and BIGINT identity keys keep those rows and their indexes small.

**Trade-off:** Two key types to remember. The rule is short: if it has its own URL, it gets a UUID.

**In one sentence:** Unguessable IDs where users see them, compact IDs where they do not.

---

## D22: Quantity and unit price keep four decimals; amounts keep two

**Alternatives:** Two decimals for every money-like column, as the general rule in CLAUDE.md says.

**Why:** Real invoices quote unit prices like 0.125 per item or 3.3333 per hour. Rounding them to two decimals would make rule R04 (quantity times unit price equals amount) fail on correct invoices. So `quantity` and `unit_price` are `NUMERIC(14,4)`. Every amount that is actually charged (`subtotal`, `tax`, `total`, line `amount`) stays `NUMERIC(14,2)`. No column uses floats.

**Trade-off:** One exception to remember. It refines the money rule; it does not break it.

**In one sentence:** Charged amounts are exact to the cent, and rates keep the precision the supplier printed.

---

## D23: The full-text `search_vector` is filled by application code

**Alternatives:** A generated column (`GENERATED ALWAYS AS (to_tsvector(...)) STORED`), or a database trigger.

**Why:** The searchable text should include line item descriptions, which live in another table. A generated column can only read its own row. A manual correction must also refresh the search text. Doing it in Python, in the same place that saves the invoice, keeps the logic visible and testable. A GIN index makes the search fast.

**Trade-off:** Every code path that changes an invoice must refresh the vector. Phase 4 puts that in one function and tests it.

**In one sentence:** The search text spans two tables, so the code that writes them also builds it.

---

## D24: Two health endpoints: liveness without the database, readiness with it

**Alternatives:** One endpoint that always checks the database.

**Why:** Render calls the health check during every deploy. If that check needed the database, a paused Supabase project would block deploys of a working API. So `/api/health/live` only proves the process is up, and Render uses it. `/api/health` also runs `SELECT 1` and returns 503 when the database is down. The frontend calls that one to show "API healthy, database connected". Errors are logged by type only, because driver messages can contain host names.

**Trade-off:** Render can route traffic to an instance whose database is down. The frontend shows that state clearly instead of hiding it.

**In one sentence:** The platform checks that the process lives; people check that the whole system works.

---

## D25: Migrations run in `start.sh`, and the container stops if either process dies

**Alternatives:** Render's pre-deploy command (paid plans only), or running migrations by hand.

**Why:** The free plan has no pre-deploy step. `start.sh` runs `alembic upgrade head` before it starts the API and the worker, so the schema always matches the code. The script then waits on both processes. If one exits, it stops the other and exits with an error, so Render restarts the whole container instead of leaving a half-working service. A normal stop signal exits cleanly. `docker-compose.yml` uses the same script with `api` and `worker` modes.

**Trade-off:** With several instances starting together, two could race to migrate. This deployment has one instance. At scale, migrations would move to a release step.

**In one sentence:** One instance can safely migrate at start, and a half-dead container restarts as a whole.

---

## D26: Supabase Session pooler, with psycopg prepared statements turned off

**Alternatives:** Supabase's direct connection, or the transaction pooler with default driver settings.

**Why:** The direct connection uses IPv6, which Render's free services cannot reach. The Session pooler works over IPv4. psycopg 3 prepares statements after a few runs, and the transaction pooler rejects that, so the engine sets `prepare_threshold=None`. That keeps both pooler modes working. Each process keeps a small pool (three plus two overflow) to stay inside Supabase's free connection limit.

**Trade-off:** Prepared statements would save a little parsing time per query. The gain is negligible here.

**In one sentence:** Use the connection path Render can actually reach, and keep the driver compatible with any Supabase pooler mode.

---

## D27: Exact dependency pins compiled with `uv`

**Alternatives:** Loose ranges in `requirements.txt`, Poetry, or `uv` with `pyproject.toml` and a lock file.

**Why:** `requirements.in` lists the direct dependencies. `uv pip compile` turns it into `requirements.txt` with every transitive package pinned. Docker, CI and reviewers all install the same versions with plain `pip`, which every reviewer already has. The frontend pins exact versions in `package.json` and commits `package-lock.json`. The backend image is pinned to `python:3.12.16-slim-trixie`, and the database image to `pgvector/pgvector:0.8.7-pg17`.

**Trade-off:** Updates are manual. That is the point: nothing changes between the test run and the deploy.

**In one sentence:** Every environment installs exactly what CI tested.

---

## D28: CI builds the Docker images and runs the whole stack

**Alternatives:** Test only the Python and TypeScript code, and trust the Dockerfiles.

**Why:** The builder has no local machine, and the cloud sandbox blocks the Debian package mirror, so a full image build cannot run there. CI fills that gap. A `docker` job builds both images, checks that Tesseract is installed, starts `docker compose`, and confirms that the API reports a connected database, the worker started and the web app answers. If the Dockerfile breaks, CI fails before Render does. CI and compose use Postgres 17 with pgvector, to stay close to Supabase.

**Trade-off:** The CI run takes a few minutes longer.

**In one sentence:** What reviewers will run locally is tested on every push.

---

## D29: A Render Blueprint (`render.yaml`) describes the backend service

**Alternatives:** Create the service by hand in the Render dashboard.

**Why:** The builder works from a phone. The blueprint sets the Docker paths, the Singapore region, the free plan, the liveness health check and every environment variable name. Render asks for the secret values in its own dashboard, and it generates `JWT_SECRET` itself, so no secret passes through chat or Git. A build filter skips backend deploys for frontend-only changes.

**Trade-off:** Blueprint changes need a sync in Render. Manual setup still works; the file then serves as the written record of the settings.

**In one sentence:** The service settings live in Git, and the secrets never do.

---

## D30: pg_trgm for fuzzy supplier matching

**Alternatives:** Exact match on the normalised supplier name only, fuzzy matching in Python (for example rapidfuzz) over every stored invoice, or embedding similarity on supplier names.

**Why:** The same supplier appears as "Acme Traders Ltd", "ACME TRADERS LIMITED" or "Acme Tradres Ltd" (an OCR slip) on different invoices. Exact matching misses those duplicates (rules R06 and R07) and reconciliation pairs. `pg_trgm` scores how many three-letter chunks two names share. A GIN trigram index on `invoices.supplier_norm` lets the database find close names fast, without loading every invoice into Python. Embeddings measure meaning, not spelling, and cost an API call per name. The database only proposes candidates; Python with `Decimal` still decides whether numbers, dates and totals match (D09). Supabase already has the extension enabled in its `extensions` schema. The migration runs `CREATE EXTENSION IF NOT EXISTS pg_trgm`, which is a no-op there and creates it in CI and docker-compose.

**Trade-off:** The similarity threshold needs tuning on the evaluation set. Trigrams are weak on very short names, so Phase 3 normalises names (case, punctuation, suffixes like "Ltd") before comparing. Fuzzy matching becomes tied to PostgreSQL.

**In one sentence:** The database finds suppliers that look alike, and code decides whether the invoices really match.

---

## D31: Gemini models: Flash-Lite for text, Flash for vision, gemini-embedding-2 at 768 dimensions

**Alternatives:** One model for every call, a larger model for text extraction, or the embedding model's full output size.

**Why:** Sowan confirmed the names against Google's model list on 4 November 2026. They live in environment variables (`GEMINI_MODEL`, `GEMINI_VISION_MODEL`, `GEMINI_EMBED_MODEL`), never in code.

`gemini-3.5-flash-lite` does text extraction. It is the highest-volume call, one or more per page window, so it uses the cheapest and fastest tier, which matters most under free-tier rate limits. The job is reading values that are already in the text, and code checks every value afterwards (D09, D10), so a smaller model's mistakes get caught instead of trusted.

`gemini-3.8-flash` reads page images, but only when Tesseract confidence is below the threshold (D07). Those pages are few and the hardest to read, so a stronger model is worth its cost there.

`gemini-embedding-2` creates the search embeddings, called with `output_dimensionality=768` to match `EMBED_DIM` and the `vector(768)` column (D19). 768 keeps the HNSW index possible and the rows small. The index uses cosine distance, which ignores vector length, so the shortened vectors need no extra normalisation step.

This embedding model has no `task_type` parameter. The text itself says what it is, with these exact prefixes:

```
query:     task: search result | query: {query}
document:  title: {title} | text: {text}
```

Search queries and stored invoices must both use them, or the similarity scores lose meaning. The templates go in `backend/app/extract/prompts.py` with the other prompts (CLAUDE.md, AI rule 7). Phase 4 decides what the title and text of each invoice contain, and tests the format.

**Trade-off:** Flash-Lite may miss values on messy layouts. The Phase 6 evaluation reports accuracy per field. If it falls short, moving `GEMINI_MODEL` up a tier is a configuration change, not a code change. Changing the embedding model or `EMBED_DIM` means re-embedding every invoice, plus a migration for a new size (D19). The prefix format belongs to this model, so a new embedding model means checking its format first.

**In one sentence:** The cheap model does the bulk reading, the strong model handles only the hard pages, and the embeddings stay small enough to index.


---

## D32: One storage interface; Supabase Storage in production, local disk for compose and tests

**Alternatives:** Supabase Storage everywhere (compose would need a Supabase project), local disk everywhere (Render's free disk is wiped on every restart), or the `supabase` Python client.

**Why:** `FileStorage` has three methods: `upload`, `download` and `delete`. `SupabaseStorage` calls the Storage REST API with `httpx2`. `LocalStorage` writes to a folder, which is a shared volume in docker-compose. `STORAGE_BACKEND` picks one; unset, it means `supabase` in production and `local` elsewhere, so a reviewer can run the whole stack with no Supabase account. The `supabase` client is banned anyway (D17), and the REST API needs only three calls.

The key in `SUPABASE_SERVICE_ROLE_KEY` is a new-style secret key (`sb_secret_...`), not a JWT. Supabase's API key guide says such a key goes in the `apikey` header only; sent as `Authorization: Bearer`, it is parsed as a JWT and rejected. So the client sends `apikey` and no `Authorization` header, and a unit test checks every request for this. The gateway swaps the key for a service role token before the request reaches Storage.

Storage keys are always `<document uuid>/original.<ext>`, where the extension comes from the detected type. A regular expression rejects any other key, which blocks path tricks in the local backend. Uploads set `x-upsert: true`: the keys are fresh UUIDs, so overwriting is safe, and a retried upload after a lost response succeeds instead of failing with "already exists". Network errors, 429 and 5xx are retried three times with backoff. Error messages carry only the operation and the HTTP status, never the key or a response body.

**Trade-off:** Local and Supabase backends can drift apart in behaviour. The Supabase client is tested only against a fake transport here; the first real call happens on Render. A missing Supabase setting fails when storage is first used, not at startup, so a misconfigured deploy still serves `/api/health`.

**In one sentence:** Callers see one small interface, production files live in the private bucket, and the secret key travels the way Supabase documents for non-JWT keys.

---

## D33: Readers return one structure; pages stream, sheets come whole

**Alternatives:** One reader that returns everything at once, or a separate output format per file type.

**Why:** PDFs and images become `PageContent` (page number, text, method, OCR confidence). Spreadsheets and CSV files become `SheetContent` (headers, rows of text, and the source row number of each row). Later stages read these and never care which reader made them (CLAUDE.md coding rule 2). Pages come from a generator, so the worker saves them in batches of `PDF_PAGE_BATCH_SIZE`, and only one rendered page image exists at a time. Sheets are returned whole, because a 50 MB upload limit bounds them and header detection needs the top rows.

`probe` runs first and cheaply: size, type by magic bytes, encryption and page count. A file that breaks a limit fails before any OCR runs. File type comes only from the bytes: `%PDF-` in the first kilobyte, the JPEG, PNG and TIFF signatures, a ZIP that holds `xl/workbook.xml`, an OLE2 file with a `Workbook` stream, or text that splits into the same number of columns line after line. The extension is ignored, and the readers open files by handle, so a download saved without an extension still reads (a test caught openpyxl refusing exactly that).

Two failure codes were added to the list in PHASES.md: `ENCRYPTED_FILE` for password-protected workbooks, and `TOO_MANY_FILES` for an oversized batch. A file that fails at upload is still recorded as a `failed` document with its code, so the batch goes on.

Cell values become text without losing precision: floats go through `Decimal(repr(x))`, dates become ISO 8601. Phase 2 parses money from that text with `Decimal`.

**Trade-off:** `.xlsx` files open in openpyxl's normal mode, because read-only mode cannot see merged cells. Normal mode holds the whole workbook in memory. A ZIP check rejects workbooks larger than `MAX_UNZIPPED_MB` once unpacked, which blocks zip bombs. Sheet rows are not stored in the database: Phase 2 reads them again from storage when it maps columns.

**In one sentence:** Every file becomes pages or sheets of text, pages stream to keep memory flat, and type comes from the bytes alone.

---

## D34: OCR cleanup: median blur, projection-profile deskew, adaptive threshold

**Alternatives:** OpenCV's `fastNlMeansDenoising`, deskew from `minAreaRect` over all ink, Otsu's global threshold, or Tesseract on the raw image.

**Why:** A page is OCR'd when it has fewer than `SCANNED_PAGE_MIN_CHARS` letters and digits of real text. It is rendered at `OCR_DPI` in grayscale, then cleaned in a fixed order. Small images are upscaled to at least 1,600 pixels wide, since Tesseract reads small text badly. A 3 by 3 median blur removes scanner speckle; non-local means denoising is far slower on a 300 DPI page and the Render CPU share is small. Deskew rotates a small copy of the page through -10 to +10 degrees and keeps the angle where the rows of ink are sharpest (highest variance of row sums), coarse then fine. `minAreaRect` fits one box around all ink, and an invoice's ink is not one rectangle. An adaptive threshold handles shadows and uneven light on phone photos, where one global threshold fails.

Tesseract runs once per page with `image_to_data`, which gives the words and a confidence for each. The page confidence is the mean over real words. On the test scans it is 87 to 95 for light noise and about 45 for heavy noise, so the `OCR_CONFIDENCE_THRESHOLD` of 60 separates them, and Phase 2 sends the heavy one to Gemini vision. A Tesseract timeout gives the page empty text and confidence 0, which routes it to vision too instead of failing the document.

**Trade-off:** The deskew search costs about 50 small rotations per page. Text rotated more than 10 degrees, or upside down, is not corrected. The thresholds are tuned on synthetic scans; Phase 6 measures them.

**In one sentence:** Cheap, predictable cleanup steps, chosen for messy invoice layouts and a small CPU, with a confidence score that decides when the vision model takes over.

---

## D35: The dataset generator builds the test fixtures; no binary fixtures in Git

**Alternatives:** Commit sample PDFs, images and workbooks to `backend/tests/fixtures/`, or hand-make each test file inside its test.

**Why:** `eval/generate/synth` draws invoices with PyMuPDF in three layouts, degrades them into scans, writes `.xlsx`, `.xls` and CSV registers, and makes the broken files (truncated, encrypted, empty, renamed, a Word ZIP, a damaged workbook and image). Each file gets ground truth JSON beside it, and a manifest says what ingestion must produce: a structure with page or sheet facts and text it must contain, or a failure code. pytest builds this set once per run with a fixed seed. The Phase 1 exit test reads the manifest and checks every file. Phase 6 runs the same generator at a larger scale for evaluation, so test data and evaluation data come from one source.

PyMuPDF is pinned to 1.28.2, not 2.x. Version 2 pulls in `pymupdf4llm` and `pymupdf-layout` and doubles the installed size, and the reader needs none of it.

**Trade-off:** The generator is test infrastructure that must itself be correct; its ground truth is checked by the reader tests. Synthetic files are cleaner than real ones (D13). `xlwt` is a dev-only dependency, used just to write the `.xls` fixture.

**In one sentence:** One seeded generator makes both the test fixtures and the evaluation set, so the repository holds code, not binary samples.

---

## D36: The model returns printed text; code turns it into dates, money and codes

**Alternatives:** Ask the model for ISO dates, numbers and currency codes directly, or let it fill a typed schema.

**Why:** Converting "1.234,50" or "03/10/2026" is where models slip quietly: a dropped separator or a swapped day and month gives a plausible wrong value. So the schema the model fills (`LlmExtraction`) holds every value as the string printed on the page, with a confidence from 0 to 1 and an evidence snippet. Code then parses it. `parse_amount` handles US and European separators, currency signs, brackets for negatives and "450,-", and rejects badly grouped digits like "1,2,3". `parse_date` handles ISO, numeric and month-name dates; day and month that could swap (03/10/2026) follow `DATE_DAY_FIRST` and get the flag `ambiguous_date` with lower confidence. Currency comes from codes and unambiguous signs; "$" alone becomes USD with the flag `symbol_only`. Anything that does not parse becomes null with the flag `unparsed` and confidence 0. Nothing is guessed (D10).

The evidence check (AI rule 3) runs on every field with a value. A value is proven when its snippet appears in the source text and the value appears in the snippet, ignoring case and spacing. For amounts, a number in the snippet that parses to the same value also counts, so "130.20" is proven by "Total: $130.20". An unproven value is kept but loses half its confidence and gets `evidence_not_found`; Phase 3 rule R10 sends it to review.

Each stored invoice keeps the parsed values in columns, and per field the confidence, evidence, raw text and flags in `field_meta`, plus the model's raw reply in `raw_extraction` for audit and evaluation. An amount with more than two decimals is rounded half up and flagged `rounded`; an amount too large for `NUMERIC(14,2)` is dropped and flagged `out_of_range`.

**Trade-off:** More parsing code to own and test, and a few formats (Indian lakh grouping such as 12,34,567) are rejected rather than read. Rejected values go to review, which is the safe failure. *Updated by D56: lakh grouping, Bengali digits and the "/-" ending now parse.*

**In one sentence:** The model copies what it sees, and deterministic code decides what the text means.

---

## D37: Spreadsheet rows converted in plain Python, without pandas

**Alternatives:** pandas, as D12 first planned.

**Why:** The Phase 1 readers already turn every cell into text and fix the headers. What is left is a loop: pick the mapped cells of each row and parse them with the same functions as PDF values. Rows that share an invoice number and carry line item columns form one invoice. pandas would add about 60 MB to the image and tens of MB of memory to the worker on a 512 MB instance, for no gain at this point. Column mapping still follows D12: rules first, and the model once per sheet only when a wanted field (invoice number, date, supplier, total) has no rule match and unused columns remain. The model's answer is checked: a header that does not exist, or one already used, is ignored. LLM-mapped columns get confidence 0.85 against 0.95 for rule matches.

**Trade-off:** Analytics across sheets would be easier with a data frame. Nothing needs that yet; adding pandas later is a one-line change.

**In one sentence:** The rows are already clean text, so a loop does the job without a heavy library.

---

## D38: Vision fallback transcribes the page; the text model still extracts

**Alternatives:** Ask the vision model to return invoice JSON straight from the image.

**Why:** Pages with Tesseract confidence below `OCR_CONFIDENCE_THRESHOLD` are rendered at `VISION_DPI` (largest side capped at 3,000 pixels) and sent to `GEMINI_VISION_MODEL`, which transcribes the text. The page row then holds that text with method `vision`, and keeps the Tesseract score for the record. Extraction runs the same way on every page. So there is one extraction prompt to test, segmentation still works across pages, and the evidence check compares values against what the vision model read. A direct image-to-JSON call would have no source text to check evidence against.

**Trade-off:** Two calls for a weak page instead of one, and the transcription can itself be wrong. The evidence check cannot catch a misread that is consistent in both steps. Phase 6 reports accuracy on the vision path separately.

**In one sentence:** The vision model only turns pixels into text, so every value still passes the same extraction and evidence check.

---

## D39: Windows of 8 pages with 1 page of overlap, merged by invoice number

**Alternatives:** One call per page, one call for the whole document, or windows without overlap.

**Why:** One call per page cannot see an invoice that spans pages, and a 1,000-page call exceeds any sensible prompt. Eight pages hold several invoices with room to spare, and a 1,000-page file needs about 143 calls instead of 1,000, which matters under free-tier rate limits. Each window's reply is checked: every page number it names must be one of the pages shown, or the reply is rejected and retried once with that error. Merging joins two results when they share a normalised invoice number and their page ranges touch, or when a result with no number starts on the window's first page inside the previous invoice (a continuation). The more confident value of each field wins. Line items are taken page by page so a line on the shared page is not counted twice; each line carries its page number for this. Windows whose pages are all blank make no call.

**Trade-off:** An invoice longer than the window whose number is printed only on its first page relies on the continuation rule. Two invoices on one page that both lack numbers can merge wrongly. Both cases are rare in practice; the segmentation timing and accuracy are measured in Phase 6.

**In one sentence:** Overlapping windows keep invoices whole at a fraction of the calls, and deterministic rules stitch the edges.

**Update (4 Nov):** a 37-page statement with two-page invoices (the second page repeats no number) found a bug: with windows that overlap by more than one page, a continuation page could join an invoice that starts after it. A continuation now joins only the invoice that starts closest before it and reaches its page. Tests run the statement at window sizes 8, 5 and 3 with overlaps 1 and 2; every invoice comes out with its exact page range and all its lines.

---

## D40: One Gemini client with its own retries; failures split into retryable and final

**Alternatives:** The SDK's built-in retry options, or calling the SDK directly from each module.

**Why:** Every call goes through `GeminiClient.generate` (AI rule 5). A `threading.BoundedSemaphore` of `LLM_MAX_CONCURRENCY` caps calls in flight per process. Retries on 408, 429, 5xx and timeouts back off exponentially with jitter, up to `LLM_MAX_RETRIES`. The SDK's own retries are turned off so attempts are counted once and logged. Each call logs purpose, model, prompt and output tokens, latency and attempts, never prompt or reply text, and the extraction service stores the same numbers as `llm_call` processing events, which Phase 6 sums for tokens per document. Temperature is 0 and the model gets no tools.

`generate_structured` validates the reply with Pydantic. An invalid reply is sent back with a short error summary (field paths and messages only, never the rejected values, which hold document data) and retried once (AI rule 4). Two failures raise `LlmOutputError`, and the document fails with `EXTRACTION_FAILED`, because a retry would likely fail the same way. Network and quota failures raise `LlmError`, which propagates so the Phase 4 job queue can retry the job later.

The LLM-facing schemas avoid `extra="forbid"`: the SDK would send it as `additionalProperties`, which the live API may refuse, and unknown keys are dropped on parsing anyway. A manual GitHub Actions workflow ("Gemini smoke test") runs real extraction on generated invoices, because the coding sandbox has no API key.

**Trade-off:** The semaphore limits one process, not the whole deployment; with one worker that is the same thing. A long free-tier rate limit can exhaust the retries, and the job then waits for the queue's own backoff.

**In one sentence:** One door to the model, which counts, limits and logs every call, and tells a bad answer apart from a busy server.

---

## D41: Rule severities: errors block, warnings inform

**Alternatives:** Every issue sends the invoice to review, or a numeric risk score.

**Why:** A reviewer's time is the scarce resource. An `error` means the numbers cannot be trusted as stored, so the invoice goes to `needs_review`. A `warning` is shown but does not block. The split, in plain words:

| Rule | Error when | Warning when |
|---|---|---|
| R01 | invoice number, date, supplier or total is missing | customer or tax is not shown (tax-exempt and cash receipts exist) |
| R02 | a value could not be parsed, is too large, or a total, subtotal, tax or quantity is negative | |
| R03 | line amounts do not add up to the subtotal (or to the total when neither subtotal nor tax is printed) | |
| R04 | quantity times unit price, rounded half up to cents, differs from the line amount | |
| R05 | subtotal plus tax (0 when absent) differs from the total | |
| R06 | same normalised number from the same supplier is already stored | |
| R07 | | same supplier, date and total under another number |
| R08 | the date is after today | the date is more than `MAX_INVOICE_AGE_YEARS` old |
| R09 | a required field was read below `FIELD_CONFIDENCE_THRESHOLD` | any other field was |
| R10 | the invoice number or total has no evidence in the source text | any other field has none |
| R11 | more than one currency appears on one invoice | the currency is missing |

All comparisons use `Decimal` and `MONEY_TOLERANCE` (one cent by default). A field that was present but unreadable is reported once, by R02, not again as missing by R01. Negative line amounts are allowed, since discount lines are common. Every message names the numbers involved, for example "subtotal plus tax is 136.50, but the total is 146.50", and `details` holds them as data for the interface.

Validating again replaces the invoice's open issues, so a correction can re-run it. An invoice a person has marked `reviewed` keeps that status; its new issues are still stored.

**Trade-off:** The split is a judgement call. A business that never accepts invoices without tax would make that an error; the table lives in one file and each rule is a small function.

**In one sentence:** Only problems that make the numbers untrustworthy block an invoice; everything else is visible but does not waste a reviewer's time.

---

## D42: Duplicate search narrows by an index, then compares suppliers with pg_trgm at 0.5

**Alternatives:** Exact supplier match, a higher similarity threshold, or comparing in Python against every stored invoice.

**Why:** R06 first finds stored invoices with the same normalised number (indexed), and R07 the same date (indexed) and the same total. Only then does `similarity()` compare supplier names, so the trigram work is done on a handful of rows. Measured scores: "acme traders" against "acme tradres" (an OCR slip) is 0.53, a suffix change disappears in normalisation, and unrelated names score near 0. A threshold of 0.6 missed the OCR slip. 0.5 is safe because the name is never the only evidence: R06 also needs the same number, R07 the same date and total. `SUPPLIER_SIMILARITY` sets it.

Duplicates are flagged against everything stored at validation time, across all documents. The later invoice is flagged when it arrives; the earlier one is flagged too if it is validated again.

**Trade-off:** Two different suppliers with similar names and the same invoice number would be flagged as a duplicate; a reviewer clears it in one look. Very short supplier names give unstable trigram scores (D30).

**In one sentence:** Cheap exact filters find the candidates, fuzzy names confirm them, and no rule trusts the name alone.

---

## D43: Reconciliation matches by number, then by supplier, date and total

**Alternatives:** Match by number only, or let the model pair records.

**Why:** Pass one pairs invoices with the same normalised number. Pass two pairs what is left by a similar supplier name (the same trigram formula as pg_trgm, computed in Python because both documents are already loaded), the same date and the same total within tolerance. Each pair is compared field by field with `Decimal`, and the report lists matched pairs, mismatched pairs with the differing fields, and invoices only in A or only in B. A pair found in pass two with different numbers is reported as a mismatch on `invoice_number`: that is how a misread or re-numbered invoice shows up. A number blank on one side is not a difference, since it is the reason pass two exists. Supplier names compare after normalisation, so "ACME TRADERS LIMITED" equals "Acme Traders Ltd". Results are stored in `reconciliations` as JSON.

**Trade-off:** Line items are not reconciled, only invoice-level fields. Two invoices with the same supplier, date and total but no numbers can pair the wrong way round; the totals still agree, so the report stays correct in amount.

**In one sentence:** Exact keys first, a strict three-part fallback second, and every difference shown with both values.

---

## D44: A vision outage degrades to the text model, then to Tesseract text

**Alternatives:** Fail the document (or its job) when the vision model is down.

**Why:** The first real smoke test run (4 Nov) read all four digital invoices correctly with `gemini-3.5-flash-lite`, but `gemini-3.8-flash` answered HTTP 503 (overloaded) on five tries in a row, and that one busy model failed the run. A vision call is an improvement step, not a requirement: the page already has Tesseract text. So a page whose vision call fails after its retries gets one try with `GEMINI_MODEL`, which also reads images. If that fails too, the page keeps its Tesseract text and method `ocr`, a `vision_failed` event records both errors, and extraction goes on. The low OCR confidence, and any value the model cannot prove, still send the invoice to review (R09, R10).

**Trade-off:** During an outage, poor scans are extracted from weaker text, so more of them go to review. A busy vision model costs up to two retry cycles of waiting per weak page.

**In one sentence:** A busy vision model makes a weak page go to review, not make the whole document fail.

---

## D45: Queue details: one job per document, final failures never retry

**Alternatives:** A job per stage (ingest, extract, validate), or retrying every failure.

**Why:** A `process` job runs every stage in order: ingest, extract, validate, index. Each stage already replaces its own output, so a retried job starts clean. A smaller `index` job refreshes search after a correction, so the API never waits for an embedding call. Failures split by cause. Network, storage, quota and database errors retry with exponential backoff (`JOB_BACKOFF_S`, then double) up to `JOB_MAX_ATTEMPTS`. A file that cannot be read (`ENCRYPTED_PDF`, `CORRUPTED_FILE`), a model reply that broke the schema twice (`EXTRACTION_FAILED`), and missing settings fail at once, because a retry would fail the same way. Unknown errors retry, capped by the attempt limit. A job's stored error holds the message only for DocIntel's own error types; for anything else it holds the type name, since a message could contain document data.

A running job's heartbeat is touched every `HEARTBEAT_INTERVAL_S` by a thread with its own database session. On start, and every minute, the worker re-queues running jobs whose heartbeat is older than `STALE_JOB_S`, or fails them if they have used all attempts. `POST /jobs/{id}/retry` gives a failed job fresh attempts. Every move writes a `processing_events` row, which is the history shown for each document.

**Trade-off:** A retry after a late failure (for example, during indexing) re-runs extraction and pays for those model calls again. Splitting stages into separate jobs would avoid that at the cost of more states to manage.

**In one sentence:** One job carries a document through every stage, transient failures retry with backoff, and failures that would repeat stop at once.

---

## D46: JWT login, per-IP rate limits in memory, and a body size cap

**Alternatives:** Sessions with cookies, an API gateway for rate limits, Redis-backed limits, or `slowapi`.

**Why:** `POST /auth/login` checks the demo account with a constant-time comparison and returns an HS256 token (issuer, issue time, expiry after `JWT_TTL_MINUTES`). Every route except health and login needs it. Without `JWT_SECRET` or `DEMO_PASSWORD`, login answers 503 rather than letting anyone in. Login (`LOGIN_RATE_PER_MINUTE`) and upload (`UPLOAD_RATE_PER_MINUTE`) are limited per client IP with a sliding window kept in memory; uvicorn runs with proxy headers, so the IP is the caller's, not Render's proxy. A middleware refuses a request whose declared size exceeds a full batch at the file size limit, before the body is read. A file the checks reject is stored as a `failed` document with its code, and the rest of the batch goes on.

**Trade-off:** In-memory limits reset when the service restarts and are not shared between instances. With one instance that is acceptable; several instances would need Redis or the platform's limiter. The token cannot be revoked before it expires; the short lifetime limits the damage.

**In one sentence:** Simple, standard auth and limits that fit one instance, with each limitation stated.

---

## D47: Full-text search indexes every part in two forms; semantic search shares the filters

**Alternatives:** One text configuration, a separate search engine, or semantic search without filters.

**Why:** Names, numbers and line items are indexed with PostgreSQL's `simple` configuration (codes like "INV-2026-0007" stay whole) and its `english` one (so "cartridges" finds "cartridge"). Queries use `websearch_to_tsquery` in both configurations joined with OR, so people can type phrases, OR and -word. A test found that indexing each part in only one form let "toner -acme" still return the Acme invoice: the English half of the query negates the stemmed "acm", which was not in the index. Indexing both forms fixed it. Names and numbers rank above line items (weights A and B).

Semantic search embeds the query with the D31 query format and orders by cosine distance on the pgvector column. Both modes use the same filters (supplier, date range, amount range, currency, review status, document), applied in SQL with bound parameters. The supplier filter accepts a typo through `pg_trgm`, and `LIKE` wildcards in it are escaped.

**Trade-off:** The index is about twice as large as a single-form one, which does not matter at this size. Invoices without an embedding (no embedding model, or an embedding job not run yet) do not appear in semantic results.

**In one sentence:** Exact codes and plain-language words both match, negation works, and one set of filters narrows both search modes.

---

## D48: Corrections are trusted values with an audit trail

**Alternatives:** Overwrite the values silently, or re-run extraction after a correction.

**Why:** `PATCH /invoices/{id}` accepts only the fields sent, validated by type (dates, decimals with at most two places, three-letter currency codes). Each changed field gets a `corrections` row with the old value, the new value and the user. Its `field_meta` entry becomes confidence 1.0 with the flag `corrected`, so R09 and R10 stop firing on it. The normalised number and supplier are rebuilt, validation runs again at once, and the search vector is refreshed in the same request. The embedding is cleared and an `index` job re-embeds it. `mark_reviewed` sets the status to `reviewed`, which later validation keeps.

**Trade-off:** A corrected value is trusted completely; a wrong correction is caught only by the arithmetic rules (R03 to R05). The audit trail shows who made it.

**In one sentence:** A person's correction wins, is checked by the same rules, and leaves a record.

---

## D49: The frontend renders in the browser and talks to the API directly

**Alternatives:** Server Components that fetch on the Vercel server, a Next.js backend-for-frontend that proxies the API, or a data library such as SWR or TanStack Query.

**Why:** The browser holds the JWT and calls the Render API directly (D14), so every app page is a Client Component. Server-side fetching would need the token on the Vercel server, which means cookies and a second place that handles credentials. Pages sit in an `(app)` route group whose layout shows them only to a signed-in user; the gate renders inside a Suspense boundary, as this Next.js version requires for anything that reads the URL. The token lives in `sessionStorage`: it ends with the tab, and the API sets no cookies, so there is no CSRF surface. A 401 from any call clears the token and sends the user back to login.

One small hook (`useApi`) loads data, polls while a job runs (the documents list and the document page update by themselves), and shows a "the backend may be waking up" note when the first answer takes more than five seconds, because a free Render instance sleeps. Money stays a string from the API to the screen; only the display groups the digits. The layout is single-column cards on a phone and puts the extracted fields beside the source text on a wide screen.

**Trade-off:** No server rendering for data pages, so the first view of a page shows a short loading state. A data library would add caching and deduplication; at this size, one hook of about 60 lines is easier to read and defend.

**In one sentence:** The browser is the only client of the API, with one token, one data hook and states for loading, empty, error and a sleeping backend.

---

## D50: Known limitation: reconciliation files also trigger the duplicate rule

**Alternatives:** Exclude documents uploaded for reconciliation from R06, or mark a document as a reference copy at upload.

**Why:** A supplier statement and the company's Excel export list the same invoices by design. When both are uploaded, the later one's invoices get R06 (duplicate) errors, which is the rule working as defined in D41, and they appear in the review queue. The browser test on 4 November showed this with the reconciliation pair. Changing it needs a way to say "this file is a reference copy", which is a product decision, not a bug fix.

**Trade-off:** Some noise in the review queue when the same invoices arrive twice on purpose. The duplicate message names the matching invoice, so a reviewer clears it quickly.

**In one sentence:** The duplicate rule cannot yet tell an intentional second copy from a real duplicate, and the report says so.

---

## D51: Evaluation runs the real pipeline and scores from the database

**Alternatives:** Call the extraction functions directly on each file and score in memory, or hand-label a set of real invoices.

**Why:** `eval/run_eval.py` generates the labelled dataset, uploads every file through `register_upload`, queues it, and lets the real `Worker` process the queue, with real Gemini calls, OCR, retries and fallbacks. It then scores what the database holds, so the numbers describe the system a reviewer uses, not a shortcut through it. The scoring rules:

- Field accuracy: each true invoice is paired with a stored one by normalised number (by position when the truth has no number). Values are compared after normalisation: invoice numbers without punctuation, supplier names without case or suffixes, money as exact `Decimal`, dates as dates. A true invoice the system missed counts as wrong on every field.
- Line items: a line matches when an extracted line has the same amount; precision, recall and F1 over all PDF and image invoices (spreadsheet registers carry no line columns).
- Documents: completed, failed by cause, and broken files checked against the code each must get.
- Timing: from the processing events, job start to completion, per document and per page, split by digital, OCR, vision and spreadsheet paths; mean and 95th percentile.
- Validation: each planted error must trigger its rule. The false flag rate counts clean invoices with any error-level issue, leaving out R06 and R07, because the dataset repeats invoices on purpose (one invoice as a PDF, a scan and a TIFF).
- Tokens: summed from the `llm_call` events per document. No cost figure is printed, because the price of these models was not confirmed; tokens are the honest unit.

The workflow runs only when asked (by hand, or when `eval/eval-request.txt` changes), since it spends tokens. `--fake` runs the same code with the test suite's perfect-reader model to check the scoring without spending anything; its accuracy numbers are meaningless and the report says so.

**Trade-off:** Synthetic layouts are cleaner than real invoices (D13), so accuracy is likely optimistic. Matching lines by amount alone can pair two lines with equal amounts the wrong way round; it never inflates the count.

**In one sentence:** The evaluation measures the deployed pipeline end to end, scores with exact rules, and labels every limitation in the report.

---

## D52: A repaired PDF with damaged pages is corrupted; a blank page is not a hard page

**Alternatives:** Reject every PDF that MuPDF had to repair, or process whatever a repaired file yields.

**Why:** The first real evaluation run (4 November) showed both problems at once. A PDF cut at 30% of eight pages was rebuilt by MuPDF, which then listed all eight pages; five were empty because their content was lost. Each empty page went to OCR, scored confidence 0, and was sent to the vision model, which was overloaded, so a broken file cost minutes of retries and ended as a vague `JOB_FAILED`. Now:

- If MuPDF had to repair the file and a page then reports missing content ("format error", "cannot load", "non-page object"), the file fails at once with `CORRUPTED_FILE` and names the page. A repaired file whose pages read cleanly still goes through, because small cross-reference faults are common in real PDFs and their content is intact. A test covers each case.
- A page that is blank after cleanup (under 0.2% dark pixels) gets no OCR and no confidence (`null`), and the vision fallback skips it. A blank page has nothing to read; sending it to a vision model wastes a call and time.

MuPDF's own stderr messages are switched off and read through `mupdf_warnings()` instead.

**Trade-off:** A damaged file whose readable pages hold good invoices is rejected whole. For finance documents that is the safer failure: a cut-off file can silently miss invoices, and the person can upload a good copy.

**In one sentence:** Broken files fail fast with the right code, and blank pages cost nothing.

---

## D53: The Gemini client stays under the per-minute quota and honours the server's retry hint

**Alternatives:** Rely on retries with short exponential backoff alone (the first design), or process documents more slowly.

**Why:** In the first real evaluation run, every document that completed was extracted perfectly, but 9 of 26 failed after three attempts with Gemini errors. Digital documents finish in about three seconds, so the worker called the model faster than a free-tier per-minute quota allows, and retries after 2 and 4 seconds could not wait out a quota that refills per minute. Now the client keeps a sliding window of calls and waits before a call that would exceed `LLM_CALLS_PER_MINUTE` (12 by default, per process). On HTTP 429 it waits at least 15 seconds, or longer if the server's `RetryInfo.retryDelay` says so, capped at 60 seconds. Embedding calls are recorded as `llm_call` events too, so tokens per document include them.

**Trade-off:** A busy batch is slower by design: 12 calls a minute means about 12 single-page documents a minute. On a paid tier, raising the setting is a configuration change. The limit is per process, which with one worker is the whole deployment.

**In one sentence:** Pace the calls to fit the quota instead of retrying into it.

---

## D54: One embedding request per text, and a wrong-shaped reply is final

**Alternatives:** One embedding call per invoice, or pass the texts as a list of strings (the first design).

**Why:** Evaluation run 3 (4 November) failed every document that holds more than one invoice, with "embedding reply had the wrong shape". Running the real google-genai SDK against a fake transport showed why: a list of plain strings is sent as one content with several parts, and `gemini-embedding-2` returns one embedding for it. A list of `Content` objects, one per text, is sent as separate requests in one batch call and returns one embedding each. The client now sends that. A unit test runs the real SDK and checks the request body, so an SDK change that brings the old behaviour back fails CI.

A reply with the wrong number or size of vectors now raises `LlmOutputError`, which the queue treats as final, like a schema failure. Run 3 retried each such document three times for nothing.

**Trade-off:** None beyond the one batch call per document it already made.

**In one sentence:** Each text is its own embedding request, and a reply that cannot be right is not retried.

---

## D55: The web app is one Home screen with a live processing view, built for least effort

**Alternatives:** Keep the first design (six menu items, a separate upload page with a confirm button, progress shown only as status badges), or add a guided step-by-step wizard.

**Why:** Sowan's feedback on 4 November: people here prefer the shortest path, and the processing should be visible as it happens. The redesign:

- **One Home screen** holds everything a person does daily: a search box, a drop zone that uploads the moment files are picked (no second button), the files being processed, the invoices that need attention, and recent documents with one-tap filter chips. The separate Upload page now redirects to Home.
- **A live processing view.** Each file moves through five steps (Upload, Read, AI extract, Check, Done) with the current step pulsing and a progress count in pages or extraction windows. On Home it is shown in full; on every other screen a floating dock carries the same view, so a long PDF can be watched from anywhere. The animation respects the phone's reduced-motion setting.
- **Shortcuts.** Review items show the actual problem ("subtotal plus tax is 418.75, but the total is 428.75") with **Approve** and **Fix** side by side, so most decisions need one tap and no page change. On an invoice, each issue has a Fix link that opens the form with that field focused. A search typed on Home runs at once.
- **Phone first.** A bottom tab bar (Home, Review with a count badge, Search, Compare) replaces the scrolling top menu on small screens. The start page signs in directly and says whether the free server is awake.

The backend gained `GET /api/activity` (each document's stage from its latest history event, its progress, counts, and the review total, in one cheap call polled every 2 seconds while anything runs and every 12 seconds when idle), progress per extraction window, and the first error in the review queue.

**Trade-off:** Polling, not push: a state change shows within 2 seconds rather than at once. Server-sent events would be faster but need a long-lived connection that the free Render instance and its proxy handle less reliably. The dock adds a small amount of screen clutter while files run; it hides itself once they finish.

**In one sentence:** Drop files, watch them move, and fix or approve each problem with one tap.

## D56: Amounts parse the way Bangladesh prints them

**Alternatives:** Keep the strict thousands-only rule (D36) and send every lakh-grouped amount to review, or ask the model to convert amounts to plain numbers.

**Why:** Bangladeshi invoices write "Tk 1,25,000/-": lakh grouping (the last three digits, then pairs), a "/-" or "/=" ending, sometimes Bengali digits (৳ ১,২৫,০০০) and the word টাকা. The old parser refused all of these, so the total of nearly every local invoice over one lakh came back unparsed and flagged. The parser now accepts lakh grouping (only with commas, and only when every group is well formed), strips the "/-" ending, turns Bengali digits into ASCII before parsing, and knows টাকা, Bengali month names and Bengali digits in dates and invoice numbers. The model still copies amounts exactly as printed; only Python reads them (AI rule 1).

**Trade-off:** "12,34,567.00" used to count as malformed and now parses. A misread that happens to form valid lakh groups would no longer be caught by the parser, but the arithmetic rules (R03, R05) still catch a wrong number.

**In one sentence:** A Bangladeshi invoice should not go to review just because it is written the Bangladeshi way.

## D57: Discounts and charges between subtotal and total count in the total check

**Alternatives:** Add fixed columns (discount, shipping) to the invoice table; let the model put a combined figure in tax; or keep the rule subtotal + tax = total and accept the false flags.

**Why:** Real bills print other lines between subtotal and total: a discount, a delivery or service charge, a second duty such as SD, rounding. With only subtotal + tax = total, R05 flagged correct restaurant bills and VAT invoices. The model now copies each such line as a label and the printed amount (prompt rule 12). Python reads the amount and sets the sign from the label (discount, less, rebate, coupon, ছাড় make it negative), and R05 checks subtotal + tax + adjustments. An unreadable adjustment sends the invoice to review instead of being ignored. When no subtotal is printed, R03 adds the adjustments to the line sum. Spreadsheets map Discount, Delivery, Service charge and similar columns by rule. The lines are stored in `field_meta` beside each field's evidence, so no migration was needed, and the API returns them as `adjustments`.

**Trade-off:** The sign comes from a keyword list, so an unusual label for a deduction ("goodwill") would be added instead of subtracted; R05 then flags it for a person, which is the safe direction. Adjustments are not a column, so they cannot be filtered in SQL.

**In one sentence:** The model copies the extra lines, Python decides their sign and does the sum.

## D58: A file that is not an invoice says so

**Alternatives:** Add a classification call before extraction, or a separate document status `not_invoice`.

**Why:** For PDFs and images the extraction prompt already allows an empty answer (rule 10), so a letter gives no invoice. A spreadsheet had no such guard: a staff list with a "Date" column became one fake invoice per row. Now the column-mapping call also answers `lists_invoices`, and a sheet the model says is not invoices gives none. When the model is not asked (headers map by rule, or no key), a sheet needs a money column and two mapped fields. A completed document with no invoices gets the event `no_invoice_found`, and the web app shows "No invoice found" on Home, in the live steps and on the document page, with a hint to upload a clearer copy if it is one. No extra call and no schema change: the existing calls carry the decision.

**Trade-off:** If the model wrongly calls a real invoice register "not invoices", its rows are skipped. The sheet's stored mapping records the verdict, the document shows "No invoice found", and Process again retries it. Evaluation run 5 measures this on real Gemini.

**In one sentence:** Nothing is invented from a file that is not an invoice, and the screen says why it is empty.

## D59: Invoices download as a CSV for Excel

**Alternatives:** An .xlsx export, or only the JSON API.

**Why:** The brief says staff enter invoice data into internal systems, and in practice that means Excel or an accounting package import. `GET /api/export/invoices.csv` (optionally by review status) returns every invoice with its totals, discounts and charges, review status, open issues and source. It starts with a UTF-8 byte order mark, so Excel shows Bengali names correctly. Document text is untrusted, so any text cell that starts with = + - @ or a tab gets a leading apostrophe and cannot run as a formula (CSV injection). A button on Home downloads it.

**Trade-off:** CSV has no types or formatting, and the export is capped at 20,000 rows to stay within the free instance's memory. An .xlsx writer would add a dependency for little gain.

**In one sentence:** One tap gets the data into Excel, safely.

## D60: Prompts carry a version, and a scheduled ping keeps the free demo awake

**Alternatives:** Track prompt changes only in Git; let Supabase pause and wake it by hand before a demo.

**Why:** `PROMPT_VERSION` in `prompts.py` is stored with the model name on every document's `extracted` event, so any stored result can be traced to the prompts and model that made it, and a prompt change can be compared run to run. Supabase pauses free projects after a week without activity, which would break the live link while reviewers look at it; a GitHub Actions workflow calls `/api/health` (which queries the database) every three days, and fails, which emails the owner, if the database does not answer.

**Trade-off:** The version is bumped by hand. The ping costs a few minutes of the shared Render free hours each month.

**In one sentence:** Every result says which prompt made it, and the demo stays up between visits.

## D61: Page windows run in parallel, and a failed window tries a second model

**Alternatives:** Keep one call at a time per document; use asyncio for the model calls; retry only through the job queue.

**Why:** A 1,000-page PDF needs about 143 extraction calls (windows of 8 pages, D39). One at a time, the wait for each reply adds up, and the semaphore set by `LLM_MAX_CONCURRENCY` was never used because the worker is single-threaded. Windows now run on a small thread pool of that size. Threads fit here: the calls are I/O-bound and release the GIL, the rest of the code is synchronous (D18), and the client's semaphore and per-minute limiter (D53) already bound every call, so the free-tier quota still holds. Replies are merged in page order, whatever order they finish in, and progress is written on the worker's own thread because a database session is not thread-safe. A window whose model still fails after its retries (an overload or a quota error) tries `GEMINI_FALLBACK_MODEL`, by default the vision model, the same idea as the vision chain (D44). A reply that breaks the schema twice stays final (D40). If both models fail, the job queue retries the document with backoff (D45), and after the last attempt it shows as failed with a Process again button.

**Trade-off:** On the free tier the per-minute limit, not concurrency, sets the speed, so the gain shows on a paid tier: raising `LLM_MAX_CONCURRENCY` and `LLM_CALLS_PER_MINUTE` is a configuration change. A fallback model may cost more per token, but only for windows that would otherwise fail.

**In one sentence:** Long PDFs no longer wait for one reply at a time, and one busy model no longer fails a document.

## D62: Cost is measured from real token counts, including thinking, and shown live

**Alternatives:** Estimate cost from page counts; report tokens only; rely on the Google Cloud billing page.

**Why:** Every Gemini call already stores its purpose, model, input and output tokens and latency as an `llm_call` event. Two gaps made the cost wrong or invisible. First, Gemini 3 models can think, and Google bills thinking tokens as output; the client counted only the answer's tokens. It now records `thinking_tokens` too, and `GEMINI_THINKING_LEVEL` (unset by default) can lower thinking for extraction, which copies text and needs little reasoning. Second, nobody could see the cost without reading the database. `GET /api/stats` now sums tokens by model and prices them from a small table in `app/core/pricing.py` (Google's list prices, with the date they were checked), and also gives document success and failure rates and processing time. Home shows one line of it. A model with no listed price gives no estimate rather than a guess. Embedding replies carry no token count, so embedding tokens are estimated at four characters per token, a small share of the total.

**Trade-off:** Prices change, so the table needs a manual update; the date beside it says how fresh it is. The free tier costs nothing, so the figure shown is what the same work would cost on the paid tier.

**In one sentence:** Every call's tokens are counted, thinking included, and the app shows what the work would cost.

## D63: Security headers on every response

**Alternatives:** Rely on the hosts' defaults; add a full nonce-based CSP to the web app.

**Why:** The API returns data, never pages, so every response says so: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` (invoice data must not sit in shared caches), a deny-all `Content-Security-Policy`, and HSTS in production. The Swagger page at `/api/docs` is left without the CSP because it loads its own scripts. The web app sends a CSP that lets the browser talk only to its own origin and the API origin, forbids plugins and framing (`frame-ancestors 'none'` stops clickjacking), and allows `blob:` frames only for the original file the page fetched itself (D65).

**Trade-off:** The web app's CSP still allows inline scripts, because Next.js inlines its bootstrap; a nonce per request would remove that but needs every page rendered on the server. React already escapes all document text, and no code uses `dangerouslySetInnerHTML`.

**In one sentence:** The browser is told exactly what the app may load and that it may not be framed.

## D64: A low-confidence scan is also read upside down

**Alternatives:** Tesseract's orientation detection (`--psm 0`), which needs an extra language file and fails on sparse pages; send every low-confidence page to the vision model.

**Why:** Phone photos are often taken the wrong way up. A sideways page already read well (the cleanup and Tesseract's layout analysis handle 90 degrees: 94% confidence in a test), but an upside-down page fell to 47% and went to the slow, paid vision model. Now a page under 70% confidence is read once more turned 180 degrees, and the reading with the higher confidence wins. It costs one extra Tesseract pass (about half a second) and only on weak pages; a noisy page that is the right way up keeps its first reading. The evaluation set has an upside-down photo.

**Trade-off:** Weak pages that are simply noisy pay the extra half second for nothing.

**In one sentence:** One cheap extra OCR pass beats a slow vision call for a photo taken upside down.

## D65: The original file can be viewed, and a document can be deleted

**Alternatives:** Public or signed storage links; soft delete with a flag.

**Why:** A reviewer checks a value against the page it came from, so the document page now shows the original: `GET /api/documents/{id}/file` streams the stored file through the API with the same login, and the page shows PDFs and photos inline (spreadsheets and TIFFs download). The bucket stays private and no link outlives the session (security rule 4). Deleting is the other half of handling personal data: `DELETE /api/documents/{id}` removes the stored file first and then the document row, and the database cascade removes pages, invoices, line items, issues, corrections, jobs, history and reconciliations. It refuses while a job runs, and if the file store fails it keeps the row so nothing is left half deleted. The log records only the document ID and the user.

**Trade-off:** Streaming through the API uses the free instance's bandwidth and memory for large files, where a signed URL would not. A hard delete cannot be undone; the page asks for confirmation first.

**In one sentence:** Reviewers see the real page, and data can be removed completely when it must be.

## D66: Mark files, then upload; mark documents, then act on them

**Alternatives:** Keep the upload-on-pick drop zone (D55); add a separate bulk page.

**Why:** Two needs from Sowan's review. First, on a phone, photos come from the gallery and PDFs or Excel files from the Files app, and one picker cannot reach both, so a mixed batch needs more than one pick. Picking now adds files to a list; each shows its type (PDF, Photo, TIFF, Excel, CSV), its size and a checkbox, and files the server would refuse (an unsupported type, an empty file, over 50 MB) are shown as such and cannot be marked. "Upload N files" sends the marked ones together; more than 20 go in batches of 20, the server's batch limit. The server still checks every file by its bytes (security rule 5). Second, the document list has a checkbox per row and "Mark all on this page", and the marked documents can be processed again, downloaded for Excel (the export takes `document_id` filters), compared (exactly two), or deleted. The Failed filter adds "Retry all failed".

**Trade-off:** Uploading is now two taps (pick, then upload) instead of one; the second tap is what lets a person check and mix files before sending. Bulk actions call the existing endpoints once per document, which is simple and reuses their checks, but slower than a bulk endpoint for hundreds of files.

**In one sentence:** Gather files of any type from anywhere, tick what to send, and act on many documents at once.

## D67: A model that just failed is skipped for five minutes while a fallback exists

**Alternatives:** Keep retrying every model on every page; a full circuit breaker in the client for every call.

**Why:** In evaluation run 6 one weak scan took 235 seconds, nearly all of it retrying `gemini-3.8-flash` (HTTP 503) before the fallback read the page. When a model still fails after all its retries, `app/extract/breaker.py` now remembers it for five minutes, and the fallback chains (vision, D44; extraction windows, D61) go straight to the next model. The last model in a chain is always tried, so the breaker can shorten a wait but never turns a slow success into a failure; a success closes it at once. The state lives in the worker process.

**Trade-off:** For five minutes the preferred model is not tried even if it recovers sooner, so a few pages may be read by the fallback model when the better one was available.

**In one sentence:** Stop waiting on a model that is down; come back to it in five minutes.

## D68: Best match search merges keyword and meaning by reciprocal rank fusion

**Alternatives:** Keep two separate modes only; a weighted sum of the full-text rank and the cosine similarity.

**Why:** People type both exact codes ("INV-2026-00007") and loose descriptions ("printer supplies"). Full text finds codes and words; embeddings find meaning; neither does both. `mode=hybrid` takes the top 50 of each, filtered the same way, and scores each invoice by the sum of 1 / (60 + its rank) in each list. Ranks, not raw scores, are merged, because a `ts_rank` and a cosine similarity are not on the same scale and a weighted sum would need tuning against relevance labels we do not have. An invoice found by both lists rises to the top. Without the embedding model (no key, or Gemini down) it returns the keyword results instead of failing. It is the web app's default, called Best match; an empty query lists everything that fits the filters.

**Trade-off:** Each hybrid search runs both queries and one embedding call, so it costs a little more than either alone. Only the top 50 of each list can appear.

**In one sentence:** Codes and descriptions both find what they mean, with no weights to tune.

## D69: Bengali scans go to the vision model, not to a Bengali Tesseract pack

**Alternatives:** Install Tesseract's Bengali pack and read pages with `eng+ben`.

**Why:** Measured on 5 November. With the Bengali pack, a Bengali invoice page read at 86 to 90% confidence and names came out right, but Bengali digits on short amount lines were read as Latin look-alikes: "৪০০.০০" became "800.00" and "১,৪০,২৫০.০০" became "$,80,2¢0.00", while the page confidence stayed high. A high-confidence page never reaches the vision model, so a confident wrong amount would go straight into the data. With English only, Tesseract reads a Bengali page at about 35% confidence, below the 60% threshold, and Gemini vision reads it, digits included. The change was reverted, and a test now checks that a Bengali page reads weakly so it takes the vision path. Bengali digits and month names already parse once read (D56).

**Trade-off:** Bengali scans cost a vision call each and wait for it; on the free tier that can be slow when the vision model is busy (D67 shortens the wait).

**In one sentence:** A slower correct reading beats a fast confident wrong one.

## D70: Scaling is measured with a load test on the real queue

**Alternatives:** Claim scalability from the design alone; a load test against the live free instance.

**Why:** The brief asks for scalability, and the claim that more workers mean more throughput should be a number. `eval/load_test.py` uploads the same 24 invoices for 1, 2 and 4 workers and times how long they take to drain the real Postgres queue, with a fake model that waits 2 seconds a call (Gemini's measured latency, D62). Result: 1.0x, 2.0x, 3.8x. It also asserts that every document completed, so a lost or doubled job would fail the run. The live free instance is not used: it has one CPU and a shared monthly allowance, and its numbers would measure the free plan, not the design.

**Trade-off:** Workers run as threads in one process, which is fair for waiting on the model but not for OCR-heavy batches, where separate processes or containers would be needed (`docker compose up --scale worker=3`).

**In one sentence:** Twice the workers, twice the documents a minute, measured rather than claimed.
