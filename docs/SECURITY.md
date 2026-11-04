# Security

What DocIntel protects today, and what a production deployment would add. Every point here is implemented and, where possible, tested.

## Secrets

- No secret is in the repository. Values live in the Render, Vercel and GitHub Actions settings. `.env` is ignored by Git; `.env.example` holds placeholders only.
- gitleaks scans the full Git history on every push.
- Settings hold secrets as `SecretStr`, so they never appear in logs, error messages or reprs. Settings errors never echo input values, because `DATABASE_URL` holds a password.
- The Supabase secret key (`sb_secret_...`) is used only by the backend, and only in the `apikey` header of Storage API calls (D32). Render generates `JWT_SECRET` itself.
- The Gemini key stays in GitHub Actions for the smoke test and the evaluation; the coding sandbox never sees it.

## Access

- Every API route except health and login needs a JWT (HS256, issuer and expiry checked, `JWT_TTL_MINUTES`). Tests cover missing, malformed, forged and expired tokens.
- The demo password is compared in constant time. Without `JWT_SECRET` or `DEMO_PASSWORD`, login answers 503 instead of letting anyone in.
- Login and upload are rate-limited per client IP (429 with `Retry-After`).
- CORS allows only the frontend origin. The API sets no cookies, so there is no CSRF surface; the browser keeps the token in `sessionStorage`, which ends with the tab.
- The Supabase Data API is disabled, so no table is reachable through Supabase's public REST API. The frontend never talks to Supabase. The bucket is private (D17).

## Uploads

- File type comes from magic bytes, never the name or extension. Workbooks are checked for a real workbook part; OLE files for a Workbook stream.
- Size, files per batch and pages per document are limited by settings. A middleware refuses an oversized request before reading it.
- Zip bombs (`.xlsx` larger than `MAX_UNZIPPED_MB` once unpacked) and image decompression bombs (over 80 megapixels) are refused.
- Files are stored under `<document uuid>/original.<ext>`. The user's file name is kept for display only. Storage keys are checked against a strict pattern, which blocks path tricks.
- A file that fails a check is recorded as failed with its code; it never reaches the parsers.

## The database

- Every query goes through SQLAlchemy with bound parameters. The two places that build SQL fragments use inline constants only (`setweight` weights), never user input. `LIKE` wildcards in the supplier filter are escaped.
- The worker stores error messages only from DocIntel's own error types; for anything else it stores the type name, because driver messages can contain data.

## The model

- Document text is untrusted. It sits between `<<<DOCUMENT_DATA>>>` markers, any copy of the markers inside a document is removed, and the system prompt says the text is data, never instructions. The model gets no tools and runs at temperature 0.
- The model never calculates. Every check that decides whether numbers are right runs in Python with `Decimal` (D09). A value the model cannot prove from the source text is flagged for a person (D10).
- Validation retry messages describe the schema error without the rejected values.

## What goes to Gemini

- **Sent:** the text of each page window for extraction; a page image only when Tesseract is unsure of that page; the headers and five sample rows of a sheet whose headers do not map by rule; a short summary of each invoice (number, parties, total, line descriptions) for its embedding; the search query in semantic search.
- **Not sent:** the original files, file names, user names, tokens, database IDs, and pages that read cleanly by rule (spreadsheets whose headers are known need no model call at all).
- **Free tier versus paid tier.** Google's [Gemini API terms](https://ai.google.dev/gemini-api/terms) say content sent to the unpaid quota may be used to improve Google's products and may be read by human reviewers, and ask users not to send confidential or personal data. Content sent to the paid quota is not used that way and falls under Google's data processing terms. This demo runs on the free tier, so it is used only with synthetic invoices. A company deploying DocIntel must use a paid Gemini project (or Gemini on Vertex AI in its own cloud) before any real document is uploaded. The model name and key are configuration, so this needs no code change.

## Logs

Logs hold IDs, statuses, counts and timings. They never hold document text, extracted values, prompts or replies. Gemini calls log purpose, model, tokens, latency and attempts. SQL echo and per-request HTTP logs are switched off.

## What production would add

1. Single sign-on with per-user roles and audit, instead of one demo account.
2. Token revocation, or short-lived tokens with refresh.
3. Rate limits in a shared store, and a web application firewall in front of the API.
4. Malware scanning of uploads before parsing, and parsing in a separate sandboxed process.
5. Encryption keys managed by the company, and a data retention policy with automatic deletion.
6. A data processing agreement for documents sent to the model provider, or a model hosted inside the company's own cloud.
