# STATUS.md

Current state of DocIntel. Update this file at the end of every session. Newest entry at the top of the log.

## Now

**Phase:** Phases 0 to 6 done on 4 Nov 2026, and the Phase 7 documents are written. Still open: the exit tests on the live site for Phases 4 and 5, and the Phase 7 items only Sowan can do (the video, repository access, the Reply All). The final secret scan is done (CI run 84).

**Live bug, 5 Nov 12:29 Dhaka, fixed 13:30:** every upload failed with `STORAGE_ERROR`. Two causes: the client sent the key in `apikey` only, and the value in Render's `SUPABASE_SERVICE_ROLE_KEY` was not the project's `sb_secret_` key (D32). The header fix is in `main` (#2, #3), and Sowan re-pasted the key. At 07:30 UTC the live `/api/health` answered `"storage":"ok"`, and Render logged "the Supabase key is an sb_secret key, 41 characters".
**Deadline:** 8 November 2026, 03:39 Dhaka. Target submission 7 November 2026, 22:00 Dhaka.

**Live:**

- Web app: https://docintel-tan-two.vercel.app (Vercel project `docintel`)
- API: https://docintel-api-y25b.onrender.com (Render service `docintel-api`, Singapore, free plan). Docs at `/api/docs`, health at `/api/health`.
- Render and Vercel deploy automatically from `main`. Phases 1 to 7 were merged into `main` on 4 Nov 2026 (Sowan3k/AI-Powered-Document-Intelligence-System#1, merge commit `d37fe29`).
- Branches: `ccr-2f4fe3f2-hzma97` is `main` (after #6) plus D82, evaluation run 8 and the README screenshots. Merging it into `main` deploys the photo change.

**Supabase (set up by Sowan):** `vector` and `pg_trgm` in the `extensions` schema, private bucket `documents` (50 MB), Data API disabled. `SUPABASE_SERVICE_ROLE_KEY` holds an `sb_secret_` key, sent in the `apikey` and `Authorization` headers (D32, fixed 5 Nov).

**Gemini (confirmed by Sowan, 4 Nov):** `gemini-3.5-flash-lite` (text), `gemini-3.8-flash` (vision), `gemini-embedding-2` at 768 dimensions. The vision model answered HTTP 503 (overloaded) in every real run; the fallback to the text model read those pages (D44). In run 8 it still failed at times.

**Evaluation run 8 (5 Nov):** every phone photo now goes to vision (D82). Photos 87.5% of fields (mild 100%, medium 100%, hard 66.7%), up from 77.8% in run 7; the one miss is a misread invoice number on a hard photo. Main set 100% on the 58 invoices that ran; Gemini overload used up the 45-minute budget before 7 files ran. See `docs/EVALUATION.md`.

**Evaluation (run 5, real Gemini):** 91 of 91 invoices, all 8 fields 100%, line items 224 of 224, planted errors 12 of 12, 1 false flag in 80 clean invoices, 4 of 4 non-invoice files empty, all 9 broken files rejected correctly, no failed documents. About $0.0015 per invoice at paid Gemini prices. See `docs/EVALUATION.md`.

**Next, for Sowan (in order):**

1. ~~Merge the storage fix and D56 to D71~~ Done (#2 and #3). ~~Fix the key in Render~~ Done; live health says storage ok.
2. Upload a few files on the live site and check they complete.
3. In Render, check these environment variables: `DEMO_PASSWORD` is set (pick one and put it in the submission email); `STORAGE_BACKEND=supabase` and the new defaults come from `render.yaml` (sync the Blueprint if Render asks). Optional: set `GEMINI_VISION_MODEL=gemini-3.5-flash-lite` while `gemini-3.8-flash` stays overloaded; weak scans then skip a wait of about a minute.
4. On the live site, check results, review, a correction, both searches and reconcile. Tell Claude Code what you see, and it will tick the exit tests for Phases 4 and 5.
5. Record the walkthrough video (3 to 5 minutes) following `docs/WALKTHROUGH.md`.
6. Decide repository access (invite the reviewers, or make it public; gitleaks scans the full history on every push and has been green).
7. Reply All to the Care Guide email with the repo link, live links, video link, CV and portfolio.

**Blockers:** None.

**Note:** Render's free instance hours are shared across the workspace with BahasaBot and grab-realtime-demo.

**Open questions:**

1. Repository access at submission: invite the reviewers, or make the repo public after a full secret scan.
2. Real public invoice samples were not added to the evaluation (licensing and personal data). The report says so.

## Session log

### 7 Nov 2026, stuck photo during the recording, and cancel (Claude Code)

During the walkthrough recording a blurred photo held the batch for over ten minutes and could not be stopped. Render logs: OCR took 2 minutes, then each vision call waited about 90 s for HTTP 504 with four retries. Not duplicate data: one job per file in Supabase. Fixed (D86): vision calls time out at 45 s with one retry, pages go as JPEG at 2,000 px, the worker runs two jobs at once, and any queued or running file can be cancelled (API and a Cancel button). Tested: 432 backend tests pass (new: cancel queued and running, vision fast fail); in Chromium at phone size, an upload was cancelled from its Home card.

### 7 Nov 2026, diagrams as images (Claude Code)

Sowan saw the README's architecture diagram as Mermaid code in the GitHub phone app, which does not draw Mermaid. All six diagrams (README, ARCHITECTURE, SCHEMA, DELIVERABLES) are now PNG images in `docs/diagrams/`, rendered in Chromium from their Mermaid sources kept beside them. The deliverables PDF was rebuilt with them.

### 7 Nov 2026, retake a blurred photo from review (Claude Code)

Sowan asked for a re-upload button in review for photos too blurred to read. Built (D85): `POST /api/documents/{id}/replace` swaps the file, keeps the document's ID and history, drops the old reading, and queues it again; "Retake photo" or "Re-upload" on every review card and on the document page. Tested: 430 backend tests pass, including a new one (refused while queued, refused for a bad file with the document unchanged, then replaced, old file removed, processed again). In Chromium at phone size: the button on a review card took a WEBP photo, converted it, uploaded it, and the card left the queue.

### 7 Nov 2026, deliverables report and PDF (Claude Code)

Sowan asked for one page or PDF with all the deliverables, linked from the README. Added `docs/DELIVERABLES.md` (each of the nine deliverables with its key results, the architecture and ER diagrams, endpoint table, phone screenshots, the quality goals and the stack differences) and `docs/DocIntel-Deliverables.pdf`, 7 A4 pages built from it in Chromium with the diagrams drawn. The README links both. The video link is still a placeholder in both; the PDF must be rebuilt when it is added.

### 7 Nov 2026, README deliverables and setup (Claude Code)

Sowan shared the brief's deliverables list. The README now has a Deliverables table (each of the nine items and where it is), the brief's quality goals with their evidence, and an Installation and setup section near the top: Docker in one command, or each part by hand, plus a check that it works. Found and fixed a trap in the old steps: copying `.env.example` to `.env` made Compose use `DEMO_PASSWORD=replace-me`, so the documented local password failed. The sample generator command was run to confirm it.

### 7 Nov 2026, photos missing from the phone's file picker (Claude Code)

Sowan's picker showed PDFs but no photos. Fixed (D84): the upload box asks for MIME types and `image/*`, not extensions alone; a file's type now comes from its MIME type when the name has no extension; WEBP, AVIF and other photos the server cannot read are converted to JPEG in the browser; HEIC that the browser cannot read gets a clear message. Tested in Chromium at phone size: a WEBP photo (converted and accepted), a PNG named "1000012345" (accepted), a HEIC file (clear message). Lint and typecheck pass.

### 7 Nov 2026, "View original" blocked on the phone (Claude Code)

Sowan tapped "View original" on a PDF and saw "This content is blocked". Cause: the PDF opened in a frame from a `blob:` link, which takes on the app's security policy, and that policy blocks Chrome's PDF viewer as a plugin. Fixed (D83): the API draws each page as a JPEG (`/api/documents/{id}/pages/{n}/image`) for PDFs, TIFF files and photos, and the page shows them as you scroll. Frames are now forbidden in the policy.

Tested: 429 backend tests pass, including a new one for page images (PDF, a two-page TIFF, a photo, missing pages, a CSV). Lint, typecheck and build pass. In Chromium at phone size, a 37-page PDF and a two-page TIFF show their pages, with no console errors.

### 5 Nov 2026, photos to vision, run 8, README screenshots (Claude Code)

Sowan asked to fix the gaps found against the brief and to add screenshots to the README like his other projects. Built D82: JPEG and PNG pages always go to the vision model (`VISION_FOR_PHOTOS`), and a page Tesseract found upside down is flipped before vision. Ran evaluation run 8: photos 77.8% to 87.5%. Refreshed `docs/TEST_REPORT.md` from CI run 84 (428 passed, 96% coverage) and ticked the final secret scan. Added 13 screenshots (desktop light and dark, phone dark) to `docs/screenshots/` and a Screenshots section to the README.

Tested: 428 tests pass in CI run 84, all four jobs green. Screenshots taken from the app running locally on demo data, in Chromium. Next: merge to `main`, so the screenshots show on GitHub and the photo change deploys.

### 5 Nov 2026, less green (Claude Code)

Sowan found the new palette too green. Green now marks only what was checked or finished; links, Approve, focus rings and the background light moved to ink and brass; "completed" and "processing" pills are neutral with a small dot, so only failed and needs-review stand out (D80, revised). Tested: build, lint and typecheck; every main screen at phone size in light and dark; no page errors.

### 5 Nov 2026, light and dark toggle (Claude Code)

Sowan asked for a light and dark toggle from the sign-in page on, not on the opening page. Built (D81): the theme lives in `data-theme` on `<html>`, set before the first paint; the colour tokens and Tailwind's `dark:` variant read it; a sun and moon button on the sign-in page and in the app's top bar switches it with a circle reveal and saves the choice.

Tested: build, lint and typecheck; in Chromium at phone size: with no choice the theme follows the phone; a tap on the sign-in page switches to dark (screenshot mid-circle), saves it, survives a reload and applies on the opening page, which shows no toggle; the app's toggle switches back; the browser's theme-color follows; no console errors or hydration warnings.

### 5 Nov 2026, finance palette and type system (Claude Code)

Sowan said the blue and purple looked AI-generated, asked about finance fonts and consistent sizes, and shared a red, cream and navy type specimen. Changed (D80): ink navy, warm paper, a ledger green brand, brass for decoration, amber and red kept for review and problems; IBM Plex Sans, Barlow Semi Condensed and IBM Plex Mono from the app; six type roles in `globals.css`; about 100 blue and purple uses replaced in 19 files; the app icon redrawn. The glass is unchanged.

Tested: lint, typecheck and build; every main screen at phone size in light and dark (opening page at three points, sign-in, Home, Home list, Review, Compare) and desktop (opening page, sign-in, Home) on a local API; the fonts load from the app; no page errors. CPU slowed four times: Home 60 fps, opening page 57 fps. A search for raw colour values found two leftovers (the sign-in glow and the preview highlight), both fixed.

### 5 Nov 2026, upload box light and the comparison list (Claude Code)

Sowan asked for a rotating light on the upload box's border and a better way to show a comparison. Built (D79): a light that travels around the upload box with a soft glow, run by the graphics chip and paused off screen; the Compare result as one list with a share bar, counts that filter, one line per invoice with problems first, and mismatched pairs opened to show A, B and the exact change.

Tested: lint, typecheck and build; screenshots on a local API with a pair that has every outcome (1 mismatched, 1 only in A, 1 only in B, 2 matched), light and dark, with the "Only in A" filter on; the border light at two moments; no page errors, no sideways overflow; Home at 60 fps with the light running, CPU slowed four times. The exact change helper was checked by hand on six pairs of amounts, including signs and different decimal places.

### 5 Nov 2026, bars drifting while scrolling (Claude Code)

Sowan saw elements move toward the screen's edge while scrolling. Cause, measured: the rotating glint layers were larger than their glass and widened the page by 3 px at some scroll positions, so the page could be panned sideways. Fixed (D78 note): the light layers are clipped to their glass, and the page cannot scroll sideways (`overflow-x: clip` on `html`). Tested: extra page width 0 on Home, Review, Search, Compare and the opening page at five scroll positions with the phone tilted; the app's top bar and the opening page's stage still stick.

### 5 Nov 2026, glass that answers to tilt and touch (Claude Code)

Sowan described the rest of Apple's material: reflections that follow the gyroscope and a ripple under the finger. Added (D78): the glints and sheen follow the phone's tilt (Chrome on Android, no prompt) or the mouse; a press sends a ring of light and, in Chromium, a wave of distortion through the refraction filter. The light now sits on two small layers inside each piece of glass and moves by transform only.

Tested: lint, typecheck and build; screenshots of a press (three frames) and of a tilt from synthetic orientation events, light and dark, over a local API; CPU slowed four times: Home 60 fps still and 60 fps with constant tilting (35 fps before the layers), opening page 58 fps; no page errors. A negative ring size on the first frame of a ripple was found in testing and fixed.

### 5 Nov 2026, glass like a drop of water (Claude Code)

Sowan said liquid means the light behind the glass blends as the page scrolls, like a water drop on the screen. Changed (D77): the displacement map is now a dome across each bar, so content under it magnifies and squeezes at the rim as it scrolls; three channel passes leave a thin colour fringe; a CSS scroll-driven animation moves the rim's light with the page (off on the opening page); labels on glass carry a soft halo.

Tested: lint, typecheck and build; close-ups of the tab bar over a moving list from a local API, light and dark; a browser trace that ruled out a JavaScript version of the moving light (about 50 extra style passes); CPU slowed four times: Home 57 to 58 fps, opening page 58 fps.

### 5 Nov 2026, liquid glass (Claude Code)

Sowan said the glass looked frosted, not like iOS liquid glass. Rebuilt the material (D76): a light tint, 3 px of blur on bars and pills, a bright gradient rim, and in Chromium real edge refraction from a displacement map per element (`frontend/lib/liquid-glass.ts`). The app's top bar is now floating glass pieces over a fading scroll edge. On the opening page the bar's text turns light over the dark card.

Tested: frontend lint, typecheck and build; screenshots at 412 by 860 in light and dark over real content from a local API with 42 demo documents (Home, Search, the opening page), desktop at 1280 by 800 (Home, Review, sign-in), a page change with the bar pieces held still, and no page errors. Scroll on the opening page, CPU slowed four times: 59 fps.

### 5 Nov 2026, opening page fixes after Sowan's phone test (Claude Code)

Sowan tested the live opening page on his phone: the scroll lagged, long stretches showed an empty blue card, there was no sign to scroll, and on `/login` the form sat below the preview. Fixed (D75): the hero animates only transforms and opacity, sticks with CSS `position: sticky` instead of a GSAP pin, and scrolls two screens instead of 7,000 pixels, with the content inside the card the whole time. The card peeks up at rest with a "Swipe up to see it work" pill. On a phone the sign-in form now comes first.

Tested: frontend lint, typecheck and build. Chromium with the CPU slowed four times, scrolling through the hero over the same 4.7 s: before 40 to 43 fps with frames up to 67 ms; after 58 to 59 fps, 95th percentile 16.8 ms, no frame over 34 ms. Screenshots at twelve scroll steps at 412 by 860 in dark mode, at 1440 by 900, with reduced motion, and of `/login` on both sizes. No sideways scrolling, no page errors.

### 5 Nov 2026, opening page and app icon (Claude Code)

Sowan shared a scroll-driven hero and asked for it as the opening page, with the server waking in the background, and asked for an icon. Built (D74): `/` shows the hero and starts the health check on load; a fixed top bar holds the live status and Sign in; the sign-in page carries on with the same wake state. The hero lives in `frontend/components/ui/cinematic-hero.tsx` (GSAP 3.15.0), filled by `frontend/components/landing.tsx`. New icon set: `app/icon.svg`, `app/favicon.ico`, `app/apple-icon.png`, `app/manifest.ts` and three PNGs in `public/`.

Tested: frontend lint, typecheck and build; Chromium at 1440x900 and iPhone 13 size at eight scroll positions, in light and dark mode, with reduced motion, with the API asleep and with a stand-in healthy API. No sideways scrolling, and no console errors apart from the refused calls while the API was down. The wake seconds carried over from the opening page to sign-in (9 s, then 11 s). Fixed from the screenshots: the brand line and the call to action sat under the top bar on a phone, the ring label was cut, and the second headline line wrapped.

### 5 Nov 2026, premium interface and Compare picker (Claude Code)

Sowan's review after his live test: picking documents to compare from a long list is slow, the sign-in page is plain although it is where a reviewer waits for the free server, and the app should feel like iOS with motion. Built (D72, D73): suggested pairs on the Compare page from a new `GET /api/reconcile/suggestions`, a search-and-filter picker sheet backed by `q` and `kind` on `GET /api/documents`, a swap button and animated results; glass bars, tab bar, dock and sheets on a field of soft light; page slides with React ViewTransition and in-page motion with Motion 14.4.0; a sign-in page with a wake-up pill and timeline from the real health check and a looping preview of one invoice being read and checked. The background image slot is `frontend/lib/brand.ts`.

Found and fixed on the way: a transition name on a wrapper stopped the glass blur; and an existing test, `test_embedding_supports_cosine_distance`, failed once the new tests ran first, because rolled-back inserts left dead entries in the HNSW graph and the approximate index scan returned no row. The test now ranks without the index. The real semantic search query was checked too: its plan ranks exactly and does not use the HNSW index, so dead entries cannot hide results. A new test guards that.

Tested: backend suite, frontend lint, typecheck and build, and Chromium at iPhone 13 size in dark and light mode against the real API on seeded data: sign-in while the server "wakes" (health delayed 7 s), sign-in, Home, Review, Compare suggestions, the picker with search and the Excel filter, a comparison with the expected 2 matched, 1 mismatched, 1 only in A and 1 only in B. No console errors, no sideways scrolling.

### 5 Nov 2026, live storage bug, phone photo set (Claude Code)

Sowan uploaded 12 files on the live site at 12:29 Dhaka. All failed with `STORAGE_ERROR`. Supabase's storage log gave the cause: `FST_ERR_VALIDATION`, "headers must have required property 'authorization'". The client sent the secret key in `apikey` only, and the fake transport in the tests never checked headers, so CI stayed green. Fixed (D32): both headers on every call, a fake that answers like hosted Storage (401 without `apikey`, the same 400 without `Authorization`), Storage's error code in our error messages, and a storage check in `GET /api/health` (list one object, 5 s timeout, cached 15 s, 503 on error). The start page now says "file storage unavailable" when that part is down. Supabase's own Python client (2.34.0) sends the same header pair. The sandbox cannot reach supabase.co, so the live health check is the real proof.

Earlier in the session: checked the build against the Care Guide email and brief, and found that `main` lacked the 25 commits on `sowan/admiring-gates-y0oyrm`. Rebuilt this branch on top of them. Added nine phone photos at three levels, scored apart from the main numbers, plus a count of wrong invoices that reached the review queue (D71). Run 7 is requested.

Then rewrote the README in Sowan's style: the brief task by task and the nine deliverables with where each lives, the brief's speed, scale, reliability and security goals with measured numbers, and why the build differs from the suggested stack. Fixed the email draft in `docs/WALKTHROUGH.md`: the subject is "Re: Interview Task Assignment", and the CV checklist now matches the email.

Tested: 412 backend tests (ruff clean), frontend lint, typecheck and build. Seven storage tests fail when the old header code is put back.

### 5 Nov 2026, more files at once, search, safety and scale (Claude Code)

Sowan asked to mark and submit many files of mixed types, plus the other suggestions. Done, each with tests: an upload list that gathers files from several pickers, shows each type, refuses unsupported ones, and uploads the marked ones in batches of 20; checkboxes on the document list with Process again, Download marked for Excel, Compare these two, Delete and Retry all failed (D66). A model that failed after its retries is skipped for five minutes while a fallback exists (D67). Best match search merges keyword and meaning by rank fusion and is the default (D68). The source text highlights where each value was read. Security headers (D63), upside-down scans flipped in OCR (D64), View original and Delete (D65), the walkthrough script and email draft (`docs/WALKTHROUGH.md`), and the `demo-files` CI artifact. The Bengali Tesseract pack was measured and rejected: it read Bengali "৪০০.০০" as "800.00" at high confidence (D69). A load test on the real queue gave 1.0x, 2.0x and 3.8x throughput with 1, 2 and 4 workers (D70). Evaluation run 6 repeated run 5 with 0 thinking tokens and per-call latency (extraction 21 s mean).

Tested: backend suite, frontend lint, typecheck and build, and phone-size browser walk-throughs of the upload list (6 files from two picks, one refused, one unticked, 4 uploaded), bulk export, compare, process again and delete, View original, the highlight and Best match, with no console errors.

### 5 Nov 2026, interview readiness fixes (Claude Code)

Sowan asked whether a non-invoice file is reported, and asked for an interviewer's check of the whole project. Found and fixed, each with tests: Bangladeshi amounts ("Tk 1,25,000/-", lakh grouping, Bengali digits, টাকা) now parse (D56); discounts, delivery and service charges and SD count in the total check, so correct bills are no longer flagged (D57); a sheet that is not invoices gives no invoices, and every empty result says "No invoice found" (D58); a CSV export for Excel with a BOM and a formula-injection guard (D59); prompt version stored per document, and a scheduled ping keeps Supabase from pausing (D60). SECURITY.md now says what is sent to Gemini and why real documents need the paid tier. The dataset gained two Mushak-6.3 style VAT invoices, a restaurant bill, a prompt-injection invoice and four non-invoice files.

Tested: 383 backend tests (coverage 96%), frontend lint, typecheck and build, a fake-model evaluation (4 of 4 non-invoices empty, 3 of 3 adjustment invoices right, 0 of 68 clean invoices flagged), and a phone-size browser walk-through: "No invoice found" on Home and the letter page, discount and delivery on the VAT invoice card with no total error, the CSV download with BOM, no console errors. Evaluation run 5 on real Gemini (44 files, 91 invoices): all fields 100%, line items 224 of 224, planted errors 12 of 12, 1 false flag in 80, 4 of 4 non-invoices empty, the injection ignored, 0 failures; 37,568 input and 48,679 output tokens, about $0.0015 per invoice at paid prices before thinking tokens.

Then, on Sowan's request to cover fallback, rate limiting, async and cost: page windows now run in parallel within the existing limits, and a failed window tries a second model (D61); thinking tokens are recorded, `GEMINI_THINKING_LEVEL` can lower them, and `GET /api/stats` plus a line on Home show rates, time, tokens and cost (D62). 388 tests, coverage 96%, CI run 41 green. Run 6 measures thinking tokens and latency.

### 4 Nov 2026, merge to main and deploy (Claude Code)

Sowan asked for the merge. Opened and merged Sowan3k/AI-Powered-Document-Intelligence-System#1 after CI run 35 was green on `669a6d2`. Merge commit `d37fe29`. Vercel production build: READY. Render deploy: build done, migrations ran (no schema change since Phase 0), API and worker started, `/api/health/live` returns 200. Not yet checked from a browser: sign-in and a real upload on the live site (this sandbox cannot reach Render or Vercel).

### 4 Nov 2026, frontend redesign and scale check (Claude Code)

Sowan's review: people here prefer minimal steps and a visible live process. Rebuilt the web app around one Home screen (search, upload on pick, live processing, needs-attention cards with the problem and one-tap Approve, recent documents with filter chips), a floating live dock on every other screen, and a bottom tab bar on phones (D55). Backend: `GET /api/activity`, extraction progress per window, and the first error in the review queue. Checked the brief Sowan sent against the build: all seven tasks and nine deliverables are covered except the video.

Scale check for the brief's 1,000-page PDFs: a 1,000-page digital PDF reads in 2.6 s with flat memory (160 MB peak); 143 extraction calls, about 12 minutes on the free tier. Scanned pages took 0.79 s each and first peaked at 290 MB; MuPDF's cache is now trimmed after every scanned page, which brought the peak to 211 MB.

Tested: 353 backend tests, frontend lint, typecheck and build, and a new Chromium walk-through at iPhone size: sign-in from the start page, 6 files picked (upload at once, empty file explained), live steps on Home and in the dock on another tab ("AI is extracting the fields: ... (+3 more, 3 waiting)", "0/6 windows"), the problem shown on the attention card, one-tap Approve, quick search, the Failed filter, no console errors, no sideways scrolling.


### 4 Nov 2026, evaluation run 4 and Phase 6 closed (Claude Code)

Run 4 (real Gemini, 15 minutes): 27 documents completed, 9 broken files correctly rejected, 0 failures, every job on its first attempt. 87 of 87 invoices with all fields 100% correct (including the 37-page statement), line items 211 of 211, planted errors 10 of 10, 1 false flag (R04) in 77 clean invoices, 75,048 tokens in total. Wrote the results into `docs/EVALUATION.md` with the weak spots and what runs 1 to 3 found, and the summary into the README. Phase 6 checklist and exit test ticked (the optional real samples were not added). Phase 7 documents ticked: README, architecture, schema, security, AI usage, design decisions. CI run 32 green: 351 tests, coverage 96%.


### 4 Nov 2026, evaluation run 3 and the embedding fix (Claude Code)

Run 3 (15 minutes, down from 26): the truncated PDF now gets `CORRUPTED_FILE` and all 9 broken files get the right code; no rate-limit failures. Completed documents again 100% on every field and line item, all planted errors caught, no false flags. But all 10 documents with more than one invoice failed at the embedding step. The SDK sends a list of plain strings as one multi-part content, and `gemini-embedding-2` returns one vector for it. Fixed by sending one `Content` per text, proven with the real SDK against a fake transport (D54). A wrong-shaped reply is now final, not retried. Run 4 requested. 350 tests pass.


### 4 Nov 2026, first real evaluation run (Claude Code)

Evaluation run 1 (GitHub Actions, real Gemini, scale 2, 35 files, 26 minutes). Every document that completed was read perfectly: 16 of 16 invoices, all eight fields 100%, line items 55 of 55, every planted error caught, no false flags on clean invoices, about 1,400 tokens per document. But 9 documents failed with `JOB_FAILED` after three attempts each, and `truncated.pdf` got `JOB_FAILED` instead of `CORRUPTED_FILE`.

Causes and fixes: the worker called Gemini faster than the free tier's per-minute quota, and short retries could not wait it out. The client now paces calls (`LLM_CALLS_PER_MINUTE`) and honours the 429 retry hint (D53). The truncated PDF was "repaired" by MuPDF into eight pages, five of them empty, which went to the overloaded vision model. Damaged pages in a repaired PDF now fail the file as `CORRUPTED_FILE`, and blank pages skip OCR and vision (D52). Embedding calls are now counted in tokens. Added a time budget to the runner so a slow run still reports. 344 tests pass.


### 4 Nov 2026, Phase 6 start (Claude Code)

CI run 21: all four jobs green on the Phase 5 commit. Phase 5 checklist ticked.

Built `eval/run_eval.py` (D51): it generates the dataset, uploads every file, lets the real worker process the queue, and scores field accuracy, line item precision, recall and F1, document outcomes by cause, timing per path (mean and p95), validation detection and false flags, and tokens per document. A dry run with the fake model checked the scoring: every planted error detected, 0 false flags on 34 clean invoices, line items 66 of 66. Three scoring bugs were found and fixed on the way: the loop stopped while retries waited on backoff, spreadsheets were scored on line items they do not contain, and two deliberate reconciliation errors were not labelled as planted. New workflow "Evaluation": runs by hand, or when `eval/eval-request.txt` changes, with the real key.


### 4 Nov 2026, Phase 5 build (Claude Code)

Built the frontend: login, upload (several files, drag and drop, live status per file), documents list (status filter, pages, polls while anything runs), document page (fields beside the source text, confidence and evidence per field, issues, line items, inline correction with "mark as reviewed", correction history, processing history with model calls and tokens, retry and process-again buttons), review queue, search (keyword or by meaning, filters), and reconcile. Loading, empty, error and sleeping-backend states on every page. Decisions D49 and D50.

Tested: lint, typecheck and production build pass. Ran the real API and worker on Postgres with the fake model, and the built web app, then drove it with Chromium at iPhone 13 size. Every step passed: redirect to login, a wrong password, upload of 7 files (5 completed, the empty and the encrypted file failed with their codes), detail page, review queue, correcting the planted wrong total (R05 cleared, status reviewed), keyword search, semantic search, reconciliation (2 matched, 1 mismatched, 1 only in A, 1 only in B), and the failed document's error. The page stayed 390 pixels wide on a 390-pixel screen. The only console error was the 401 from the deliberate wrong password.

Found on the way: quantities showed four decimals ("12.0000"), now trimmed; reconciliation said "pages 2-2", now "page 2". Known limitation recorded as D50: a reconciliation workbook that repeats PDF invoices gets R06 duplicate errors.


### 4 Nov 2026, Phase 4 build and real Gemini check (Claude Code)

Real Gemini, first run (smoke test workflow with Sowan's key): all 4 digital invoices extracted with every field right and no flags, about 650 prompt tokens each. The vision model `gemini-3.8-flash` answered HTTP 503 (overloaded) five times and failed the run. Fix (D44): a weak page now tries the vision model, then the text model, then keeps its Tesseract text. The smoke test now also runs on pushes that change extraction code, since a manual run needs the workflow on `main`. Second run: 48 of 48 fields correct on 6 invoices (4 digital, 2 in the scanned PDF), 5,692 prompt and 4,220 output tokens in total. `gemini-3.8-flash` was still overloaded; `gemini-3.5-flash-lite` read both scanned pages.

Built Phase 4: the job queue (`FOR UPDATE SKIP LOCKED`, heartbeats, stale recovery, backoff, final versus retryable failures), the pipeline (ingest, extract, validate, index), the worker, JWT login, per-IP rate limits, a request size cap, and every endpoint in PHASES.md, plus `GET /reconciliations/{id}`. Search: full text in two forms with weights, and semantic search on pgvector with the D31 query format. Upload code moved to `app/ingest/upload.py`, so the API process never loads OpenCV or PyMuPDF. Spreadsheets now process without a Gemini key, so `docker compose up` works for CSV and Excel with no keys at all. Decisions D44 to D48.

Tested in the sandbox: ruff clean, 337 tests pass (77 new), coverage 95%, `alembic check` clean. Integration tests cover every endpoint, auth failures (missing, bad, forged and expired tokens), rate limits, a job that fails three times on HTTP 503 and then succeeds after `POST /jobs/{id}/retry`, an unreadable file that fails once without retries, two workers getting different jobs under `SKIP LOCKED`, and stale job recovery. Ran the API and worker as real processes on Postgres: upload a CSV, job succeeded, keyword search found it, the worker stopped cleanly on SIGTERM. CI's Docker job now runs the same flow inside the compose stack.

CI run 19: all four jobs green, including the compose upload and search step. Phase 4 checklist ticked; the exit test waits for the live deploy.

Fixed on the way, found by tests: `setweight()` rejected the weight as a bound parameter (now an inline literal), and negated search words slipped through (D47).


### 4 Nov 2026, Phase 3 build (Claude Code)

Built `app/validate`: rules R01 to R11 as small pure functions with `Decimal` and the money tolerance, duplicate rules R06 and R07 on Postgres with `pg_trgm` similarity, a service that stores issues and sets `needs_review` on any error, and reconciliation (number first, then supplier, date and total) stored in `reconciliations`. The generator gained planted cases for R04, R08, R06 and R07, and a PDF and workbook pair for reconciliation. They are added at the end of the build, so the existing fixtures did not change. Decisions D41 to D43.

Tested in the sandbox: ruff clean, 300 tests pass (40 new), coverage 96%, `alembic check` clean. Exit test: 15 digital PDFs go through ingest, extraction with the fake model and validation. Every planted error gives exactly its rule (R05, R03, R04, R01 warnings for missing tax and customer, R08, R06, R07), and the clean invoices give no issues at all. The reconciliation of the PDF against the workbook finds the expected matched, mismatched, only-in-A and only-in-B invoices.

CI run 14: all four jobs green. Phase 3 checklist ticked.

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
