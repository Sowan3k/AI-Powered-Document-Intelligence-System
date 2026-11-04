# AI usage disclosure

This file records how AI tools were used to build DocIntel, as deliverable 9 of the brief requires. It is updated at the end of every working session.

## Tools

1. Claude (claude.ai chat): reading the brief, choosing the architecture, writing the planning files.
2. Claude Code (cloud sessions, driven from a phone): writing code, tests and documentation, phase by phase.
3. Gemini API: the runtime model inside the product for extraction, vision OCR fallback and embeddings.

## Division of work

Sowan made the architecture and scope decisions recorded in `DECISIONS.md`, reviewed each phase, and ran and checked the deployed system. Claude Code wrote most of the code under those decisions and the rules in `CLAUDE.md`. Every phase is accepted only when its tests pass in CI.

## Runtime prompts

All prompts the product sends to Gemini live in `backend/app/extract/prompts.py`. They are listed here once Phase 2 is complete.

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

AI-generated: the ingestion package (`backend/app/ingest`), the storage package (`backend/app/storage`), the synthetic dataset generator (`eval/generate/synth`), all new tests, config, compose, Render and CI changes, and decisions D32 to D35. Claude Code checked the header rule for `sb_secret_` keys against Supabase's own documentation (through the Supabase docs connector) instead of relying on memory: the key goes in the `apikey` header only.

How it was verified: ruff, 147 pytest tests including OCR with a real Tesseract and integration tests on Postgres with pgvector, a manifest-driven exit test over 26 generated files, and `alembic check`. The OCR numbers were measured, not assumed. A test caught one real bug (openpyxl rejecting a file without an extension), which was fixed. The Docker build and a real Supabase Storage call were not run in the sandbox.

