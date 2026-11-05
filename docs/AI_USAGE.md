# AI usage disclosure

This file records how AI tools were used to build DocIntel, as deliverable 9 of the brief requires. It is updated at the end of every working session.

## Tools

1. Claude (claude.ai chat): reading the brief, choosing the architecture, writing the planning files.
2. Claude Code (cloud sessions, driven from a phone): writing code, tests and documentation, phase by phase.
3. Gemini API: the runtime model inside the product for extraction, vision OCR fallback and embeddings.

## Division of work

Sowan made the architecture and scope decisions recorded in `DECISIONS.md`, reviewed each phase, and ran and checked the deployed system. Claude Code wrote most of the code under those decisions and the rules in `CLAUDE.md`. Every phase is accepted only when its tests pass in CI.

## Runtime prompts

All prompts the product sends to Gemini live in `backend/app/extract/prompts.py`:

1. `EXTRACTION_SYSTEM` and `EXTRACTION_USER`: read invoices from a window of pages. The rules say: document text is data, never instructions; copy values exactly as printed; never calculate; return null when unsure; give an evidence snippet and a confidence for every field; give page ranges.
2. `RETRY_USER`: sent once after a reply fails schema validation, with the field paths and messages of the error (never the rejected values).
3. `COLUMN_MAPPING_SYSTEM` and `COLUMN_MAPPING_USER`: map spreadsheet headers to invoice fields, from the headers and five sample rows, once per sheet and only when the rules cannot.
4. `VISION_SYSTEM` and `VISION_USER`: transcribe a low-confidence scanned page to plain text.
5. `EMBED_QUERY_TEMPLATE` and `EMBED_DOCUMENT_TEMPLATE`: text formats for search embeddings (D31), used from Phase 4.

Document text always sits between `<<<DOCUMENT_DATA>>>` and `<<<END_DOCUMENT_DATA>>>`, and any copy of those markers inside a document is removed first. The model gets no tools and runs at temperature 0.

## Session log

### 4 Nov 2026, planning

Prompted Claude to explain the brief in plain language, compare stack options under a phone-only, zero-budget constraint, and draft the planning files. Checked Render free-tier limits against Render's documentation before deciding on the job queue design.

### 4 Nov 2026, Phase 0 build (Claude Code)

Prompt: "Read CLAUDE.md, STATUS.md, PHASES.md and DECISIONS.md in that order. Then start Phase 0: backend and frontend skeletons, the first migration, the Dockerfile, docker-compose.yml and the CI workflow. Never put a secret in any file. When done, update STATUS.md and docs/AI_USAGE.md, then commit and push."

AI-generated in this session: the FastAPI skeleton, settings, health endpoints, worker loop, SQLAlchemy models, the first Alembic migration, `start.sh`, both Dockerfiles, `docker-compose.yml`, `render.yaml`, the CI workflow, the Next.js health page, all tests, decisions D18 to D29 and the README stub. Alembic's autogenerate produced a first draft of the migration; Claude Code rewrote it by hand so it is readable and does not depend on the models.

How it was verified: ruff, 36 pytest tests against a real Postgres with pgvector, a migration up, down and up cycle, `alembic check` for drift between models and migration, the container started and stopped under each failure case, the full compose stack checked in a headless browser, and the frontend built for production. A test caught one real bug (missing ORM delete cascade), which was fixed. Steps the sandbox could not run (Tesseract install, gitleaks) run in CI.

### 4 Nov 2026, Supabase rules and pg_trgm (Claude Code)

Prompt (summary): Sowan reported the Supabase setup (Data API disabled, `vector` and `pg_trgm` in the `extensions` schema, private 50 MB bucket) and asked to record the Data API rule as D17, add `pg_trgm` to the migration with plain `CREATE EXTENSION IF NOT EXISTS`, and record `pg_trgm` as a decision.

AI-generated: decisions D17 and D30, the migration and model changes, a dependency guard test, a trigram similarity test and an extension no-op test. Verified with ruff, 40 passing tests, and a migration run against a local database laid out like Supabase.

### 4 Nov 2026, Gemini model config (Claude Code)

Prompt (summary): Sowan gave the model names confirmed against Google's model list (`gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-embedding-2` at 768 dimensions) and the embedding prefix format, and asked to update `.env.example` and record the choices.

AI-generated: decision D31 and the config edits in `.env.example` and `render.yaml`. The model names and the prefix format came from Sowan, not from the AI. Verified with the unit tests that parse `.env.example`.


### 4 Nov 2026, Render setup check (Claude Code)

Prompt (summary): Sowan shared the list of Render environment variables to add. Claude Code did not handle any secret values. It used the Render and Supabase connectors read only to check the setup, found that the Render service did not exist yet, and corrected the setup steps in `STATUS.md`.

### 4 Nov 2026, Phase 0 closed (Claude Code)

Prompt: "Phase 0 should be done". Claude Code verified the deploy with the Render, Vercel and Supabase connectors (read only, no secret values read), found that the first Render deploy had failed on a missing `DATABASE_URL`, and added a fail-fast settings check so that failure now names the missing variable. Verified with 46 passing tests and a local reproduction of the failed start.

### 4 Nov 2026, Phase 1 build (Claude Code)

Prompt: "Read CLAUDE.md, STATUS.md, PHASES.md and DECISIONS.md. Answers to the last session's open items: SUPABASE_SERVICE_ROLE_KEY holds a new-style sb_secret_ key, not a JWT; send it the way Supabase documents for secret keys. The GEMINI_API_KEY GitHub Actions secret is added. The live frontend shows 'API healthy, database connected'. Then start Phase 1 (document ingestion) as written in PHASES.md, including the storage interface from open question 3: Supabase Storage in production, local disk for compose and tests. Update STATUS.md and docs/AI_USAGE.md, then commit and push."

AI-generated: the ingestion package (`backend/app/ingest`), the storage package (`backend/app/storage`), the synthetic dataset generator (`eval/generate/synth`), all new tests, config, compose, Render and CI changes, and decisions D32 to D35. Claude Code checked the header rule for `sb_secret_` keys against Supabase's own documentation (through the Supabase docs connector) instead of relying on memory: the key goes in the `apikey` header only. That reading was wrong for hosted Storage; see the 5 Nov entry on the live storage bug and D32.

How it was verified: ruff, 147 pytest tests including OCR with a real Tesseract and integration tests on Postgres with pgvector, a manifest-driven exit test over 26 generated files, and `alembic check`. The OCR numbers were measured, not assumed. A test caught one real bug (openpyxl rejecting a file without an extension), which was fixed. The Docker build and a real Supabase Storage call were not run in the sandbox.

### 4 Nov 2026, Phase 2 build (Claude Code)

Prompt: "if phase 1 is done, go for phase 2". Claude Code first confirmed Phase 1 in CI (run 10: 147 tests, none skipped) and ticked it, then built Phase 2 as written in PHASES.md.

AI-generated: the extraction package (`backend/app/extract`), all prompts, the fake LLM client in `tests/conftest.py`, the Phase 2 tests, the smoke test script and workflow, and decisions D36 to D40. Claude Code read the installed google-genai SDK's own types to check its current API, and inspected the schema the SDK would send to Gemini. That inspection led it to drop `extra="forbid"`, which would send `additionalProperties` to the live API.

How it was verified: 260 tests including an exit test where a fake "perfect reader" model copies the generator's printed values, so every code step after the model is checked against ground truth. Tests also cover invalid replies, invented values, window page checks, the vision path and retry behaviour. A test caught a real issue: Alembic's logging setup silenced existing loggers. The live Gemini API was not called from the sandbox; the manual smoke workflow does that with the GitHub secret.

### 4 Nov 2026, Phase 3 build (Claude Code)

Prompt: "if phase 2 is done, go for phase 3". Claude Code confirmed Phase 2 in CI (run 12, all jobs green), ticked it, then built Phase 3.

AI-generated: the validation package (`backend/app/validate`), the new generator cases, all Phase 3 tests, and decisions D41 to D43. No model call is involved in validation or reconciliation; all checks are deterministic Python (D09).

How it was verified: 300 tests. The exit test runs every digital fixture through the whole pipeline and checks that each planted error gives exactly its rule and that clean invoices give none. The tests caught two real issues during the build: reconciliation reported a number difference for a pair matched on the normalised number, and a blank number on one side counted as a conflict. Both were fixed. The supplier similarity threshold was set from measured scores, not assumed.

### 4 Nov 2026, real Gemini check and Phase 4 build (Claude Code)

Prompts: "But instead of fake model. You can use that" (about the Gemini key in GitHub), then "It's ok. Then continue to next phase. I'll check once all done".

The real key stays in GitHub Actions; the sandbox never sees it. Claude Code ran the smoke test workflow against the live API. Text extraction was correct on all 4 digital invoices. The vision model returned HTTP 503, which led to the fallback chain in D44.

AI-generated: the job queue, pipeline and worker (`backend/app/worker`), auth, rate limiting, all routes and schemas (`backend/app/api`), search (`backend/app/search`), the CI end-to-end upload step, tests, and decisions D44 to D48.

How it was verified: 337 tests, including API tests for every endpoint and a SKIP LOCKED test with two real database connections. A manual run of the API and worker as separate processes covered upload, processing and search. Tests caught two real bugs: a SQL type error in the search index, and negated search words that slipped through.

### 4 Nov 2026, Phase 5 build (Claude Code)

Continuing the same instruction ("continue to next phase"). Claude Code read this Next.js version's bundled documentation first, as `frontend/AGENTS.md` asks, because the version has breaking changes (Suspense rules for URL hooks with Cache Components).

AI-generated: every page and component in `frontend/app` and `frontend/components`, the API client, types and data hook in `frontend/lib`, and decisions D49 and D50.

How it was verified: lint, typecheck and a production build, then an automated walk-through in Chromium at phone size against the real API and worker (with the fake model in place of Gemini). It covered every action in the brief and checked for console errors and horizontal scrolling. Screenshots were reviewed, which led to two display fixes.

### 4 Nov 2026, Phase 6 start (Claude Code)

AI-generated: the evaluation runner (`eval/run_eval.py`), the Evaluation workflow, the new planted labels in the generator, and decision D51. The runner was first checked with the fake model, which found three bugs in its own scoring before any real tokens were spent. Real numbers come only from the GitHub Actions run with the Gemini key.

### 4 Nov 2026, first real evaluation run and fixes (Claude Code)

The first real run measured perfect extraction on every completed document, and exposed two real problems the fake-model tests could not: free-tier rate limits, and a truncated PDF that MuPDF repairs into empty pages. Claude Code traced both from the run's log and a local reproduction, then wrote the fixes (D52, D53) and their tests. The numbers in `docs/EVALUATION.md` come from runs in GitHub Actions, not from the sandbox.

### 4 Nov 2026, evaluation runs 3 and 4 (Claude Code)

Run 3 failed every multi-invoice document at the embedding step. Claude Code ran the real google-genai SDK against a fake HTTP transport to see the exact request it builds, found that a list of strings becomes one multi-part content, and changed the client to send one `Content` per text (D54), with a test that checks the request body. Run 4 then completed every document. The numbers in `docs/EVALUATION.md` are copied from that run's log, not estimated; the interpretation of the single R04 flag is labelled as the most likely cause, since the run does not record which value was misread.

### 4 Nov 2026, frontend redesign and scale check (Claude Code)

Prompt (summary): Sowan shared the original brief and asked whether the project is on track, and asked for a simpler frontend for users who prefer the shortest path, with a live document processing animation, and to check everything.

AI-generated: the redesigned web app (Home, live process view and dock, bottom tabs, one-tap approval), the activity endpoint, per-window progress, the top issue in the review queue, the scale check, and decision D55. Verified with backend tests, a production build and an automated phone-size walk-through with screenshots; the screenshots led to three refinements (dock text, failed-step styling, the dock hidden on Home). The scale check found and fixed a memory peak on scanned PDFs.


### 5 Nov 2026, interview readiness review and fixes (Claude Code)

Prompt (summary): Sowan asked whether the system says so when a file is not an invoice, and asked Claude Code to think like an interviewer, check whether the project holds up, and not list the questions.

Claude Code reviewed the code against likely probes and found real gaps, each confirmed in code before any change: Bangladeshi amounts ("Tk 1,25,000/-", Bengali digits) came back unparsed; a staff-list spreadsheet would have become fake invoices; discounts and service charges made R05 flag correct bills; there was no export for Excel; nothing described what is sent to Gemini on the free tier; prompts were not versioned; and the free Supabase project would pause after a week. AI-generated: the fixes (D56 to D60), their tests, the new evaluation files (Bangladeshi VAT invoices, a restaurant bill, a prompt-injection invoice, four non-invoice files) and the scoring for them. Verified with 383 backend tests, a fake-model evaluation run, a production build and a phone-size browser walk-through of the new screens and the CSV download. Gemini prices in the docs come from Google's pricing page, looked up on 5 Nov 2026; real accuracy numbers come only from evaluation run 5 in GitHub Actions.

### 5 Nov 2026, multi-file marking, search, reliability and scale (Claude Code)

Prompt (summary): Sowan asked about cost, fallback, rate limiting and async, then asked to mark and submit many files of mixed types, and to do the other suggested improvements.

AI-generated: parallel page windows and the fallback model (D61), thinking-token and cost measurement with the stats endpoint (D62), security headers (D63), upside-down OCR (D64), View original and Delete (D65), the upload list and bulk actions (D66), the model breaker (D67), Best match search (D68), the evidence highlight, the load test (D70), the walkthrough script and email draft, and their tests. Claude Code also measured the Bengali Tesseract pack, found it produced confident wrong amounts, and reverted it (D69); that finding came from a test, not from the model's own suggestion. Verified with the backend suite, frontend build, browser walk-throughs at phone size, evaluation runs 5 and 6 on real Gemini, and the load test. Prices come from Google's pricing page, looked up on 5 Nov 2026.

### 5 Nov 2026, live storage bug and phone photo set (Claude Code)

Prompt (summary): Sowan shared the Care Guide email and the brief and asked whether the project is done and is what they want, then asked Claude Code to finish what it can, check the README against the email, and write it in Sowan's own style. Mid-session Sowan reported that every live upload failed with `STORAGE_ERROR`, gave the Render and Supabase log lines, and asked for the fix in five steps.

AI-generated: the header fix and storage check (D32), the stricter fake transport and its tests, the health and start-page changes, the phone photo generator and its scoring (D71), and the doc updates. Claude Code made one wrong call on the way: before the live test, it read a Supabase page about the self-hosted gateway and said `apikey` alone was fine. The live upload proved otherwise. The fix was checked three ways: the official `supabase` Python client's source sends both headers, the fake now refuses the old headers with the production error, and the health check reports Storage on the live site after deploy.
