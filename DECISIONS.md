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

**Trade-off:** More parsing code to own and test, and a few formats (Indian lakh grouping such as 12,34,567) are rejected rather than read. Rejected values go to review, which is the safe failure.

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

---

## D40: One Gemini client with its own retries; failures split into retryable and final

**Alternatives:** The SDK's built-in retry options, or calling the SDK directly from each module.

**Why:** Every call goes through `GeminiClient.generate` (AI rule 5). A `threading.BoundedSemaphore` of `LLM_MAX_CONCURRENCY` caps calls in flight per process. Retries on 408, 429, 5xx and timeouts back off exponentially with jitter, up to `LLM_MAX_RETRIES`. The SDK's own retries are turned off so attempts are counted once and logged. Each call logs purpose, model, prompt and output tokens, latency and attempts, never prompt or reply text, and the extraction service stores the same numbers as `llm_call` processing events, which Phase 6 sums for tokens per document. Temperature is 0 and the model gets no tools.

`generate_structured` validates the reply with Pydantic. An invalid reply is sent back with a short error summary (field paths and messages only, never the rejected values, which hold document data) and retried once (AI rule 4). Two failures raise `LlmOutputError`, and the document fails with `EXTRACTION_FAILED`, because a retry would likely fail the same way. Network and quota failures raise `LlmError`, which propagates so the Phase 4 job queue can retry the job later.

The LLM-facing schemas avoid `extra="forbid"`: the SDK would send it as `additionalProperties`, which the live API may refuse, and unknown keys are dropped on parsing anyway. A manual GitHub Actions workflow ("Gemini smoke test") runs real extraction on generated invoices, because the coding sandbox has no API key.

**Trade-off:** The semaphore limits one process, not the whole deployment; with one worker that is the same thing. A long free-tier rate limit can exhaust the retries, and the job then waits for the queue's own backoff.

**In one sentence:** One door to the model, which counts, limits and logs every call, and tells a bad answer apart from a busy server.
