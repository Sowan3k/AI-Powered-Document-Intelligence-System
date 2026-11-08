# PROJECT_MEMORY.md

A short memory of DocIntel for future sessions. Read it after CLAUDE.md. STATUS.md holds the full log and DECISIONS.md holds the reasons behind each choice. This file keeps what is easy to forget between sessions. It holds no secrets.

## Where things stand

DocIntel was built for the Care Guide AI Engineer take-home. Sowan sent the submission email on the night of 7 Nov 2026, before the deadline of 8 Nov, 03:39 Dhaka. The repository is public. The last merge before submission is PR #13 (`fdf64ab`) on `main`.

Live: the web app at https://docintel-tan-two.vercel.app (Vercel project `docintel`), the API at https://docintel-api-y25b.onrender.com (Render service `docintel-api`, Singapore, free plan), and the database and private file bucket on Supabase. Render and Vercel deploy from `main`, so any push to `main` redeploys the live site. While the application is under review, change `main` only on Sowan's request.

Deliverables: README.md (setup), docs/DELIVERABLES.md and docs/DocIntel-Deliverables.pdf (all nine deliverables), the walkthrough video at https://youtu.be/n9xKvACPR90, and 89 decisions in DECISIONS.md (D01 to D89; D76 also has a later note on grey boxes during page changes).

Key numbers: 439 backend tests with 95% line coverage (CI run 42412092438). Evaluation run 5 got 100% of 728 fields and 224 of 224 line items on synthetic data. Run 8 got 87.5% of fields on phone photos (hard photos 66.7%). Cost is about $0.0015 per invoice.

## How Sowan works

Sowan builds from a phone only, in Claude Code cloud sessions. He reviews on a small screen, so keep summaries, commits and STATUS entries short. He writes plainly: short sentences, active voice, no em dashes, little formatting. He asks for merges himself; merge only fixes he asked for, after CI passes.

## Lessons from building it

1. The Gemini vision model (`gemini-3.8-flash`) often answers 503 or 504. Vision calls time out at 45 s with one retry, then fall back to the text model and then to the OCR text (D86). The text model is `gemini-3.5-flash-lite` and embeddings use `gemini-embedding-2` at 768 dimensions.
2. Render's free instance sleeps. The first request after a sleep can take up to a minute, and start-up with migrations takes about 38 s. The sign-in page shows the wake-up.
3. Full-size phone photos made Tesseract time out at 120 s. Fallback OCR now runs at 2400 px (D89).
4. Postgres full-text search splits `INV-2026-00026` into `inv`, `-2026` and `-00026`. Keyword search also matches the normalised invoice number and money amounts (D88).
5. Liquid glass: only Chromium draws a `url()` filter in `backdrop-filter`. A `view-transition-name` on an ancestor of a glass element stops its blur (D73). A separately named layer under refracting glass makes Chromium draw grey boxes during page changes, so the scroll edge has no name.
6. Before the fix, the Supabase key in Render was not the project's `sb_secret_` key. It has to go in both the `apikey` and `Authorization` headers (D32).
7. On 8 Nov 2026 the Render service fell asleep at 22:14 UTC and did not wake for about 15 hours: no request reached it, and the sign-in page said "Server not answering". Diagnosis: Render's wake-up failed, not the app. Every earlier wake logs `start.sh: running database migrations` within seconds, and this time nothing started and no failure event was recorded. The browser's health request was held open the full 90 s, so Render accepted it but never started the service. A manual redeploy of the same commit (Render MCP `trigger_deploy`) brought it back in about 70 s. If it happens again, redeploy first, then read the logs. A keep-alive ping or a paid instance avoids the wake-up altogether.
8. Force-pushing is blocked in these sessions. Bring the working branch up to `main` with `git merge --ff-only origin/main`.

## Working in a cloud session

1. The sandbox cannot reach Gemini or Supabase. Unit tests use the fake LLM in `backend/tests/conftest.py`. Real calls run in GitHub Actions and on Render.
2. Local Postgres: `service postgresql start`, then run pytest with `TEST_DATABASE_URL` (see the README).
3. To see app pages without a backend, run `npx next dev -p 3100` in `frontend/`. Then set sessionStorage `docintel.token` to `{"token":"x","expiresAt":<a future ms time>}` before the page loads. Playwright and Chromium are preinstalled.
4. To catch a view-transition glitch, slow the animations through CDP with `Animation.setPlaybackRate` at 0.05, then screenshot mid-transition.
5. The diagrams and the deliverables PDF are rebuilt with the scripts in `docs/tools` (`render-diagrams.js`, `build-pdf.js`).
6. The Render, Vercel, Supabase and GitHub MCP tools were connected in this project's sessions. Use them for logs, deploys and SQL instead of guessing.

## Known weak spots, if asked in an interview

The evaluation data is synthetic and cleaner than real invoices, so real accuracy will be lower. Hard phone photos are the weakest input. The vision model's overload is outside the system's control and is handled by fallbacks. The free tier's limit of 12 model calls a minute sets most of the processing time. Every trade-off is written in DECISIONS.md.
