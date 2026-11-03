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
