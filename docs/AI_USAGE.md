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

AI-generated in this session: the FastAPI skeleton, settings, health endpoints, worker loop, SQLAlchemy models, the first Alembic migration, `start.sh`, both Dockerfiles, `docker-compose.yml`, `render.yaml`, the CI workflow, the Next.js health page, all tests, decisions D17 to D28 and the README stub. Alembic's autogenerate produced a first draft of the migration; Claude Code rewrote it by hand so it is readable and does not depend on the models.

How it was verified: ruff, 36 pytest tests against a real Postgres with pgvector, a migration up, down and up cycle, `alembic check` for drift between models and migration, the container started and stopped under each failure case, the full compose stack checked in a headless browser, and the frontend built for production. A test caught one real bug (missing ORM delete cascade), which was fixed. Steps the sandbox could not run (Tesseract install, gitleaks) run in CI.
