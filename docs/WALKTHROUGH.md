# Walkthrough video script

A 4 to 5 minute phone screen recording that shows every task in the brief working on the live site. Record after the latest merge to `main` has deployed. Speak in short sentences; the captions below are what to say.

## Before recording

1. Open the API health page once (https://docintel-api-y25b.onrender.com/api/health) and wait for "connected". The free server sleeps, and the first request can take a minute.
2. Download the demo files to the phone: on GitHub, open Actions, the latest green CI run, and download the `demo-files` artifact (a zip of the synthetic dataset). Use these: `multi_invoice.pdf`, `bd_vat_invoice_0.pdf`, `planted_wrong_total.pdf`, `photo_upside_down.jpg`, `register.xlsx`, `payment_letter.pdf`, `encrypted.pdf`, `recon_statement.pdf`, `recon_register.xlsx`. A real receipt of your own also works well for the last minute.
3. Turn on Do Not Disturb, and set the screen to stay awake.

## Shot list

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Opening page | Scroll once through the hero, then tap Sign in | "DocIntel reads invoices in any form a finance team gets: PDFs, scans, phone photos, Excel and CSV. It extracts the fields with Gemini, checks every number in Python, and flags what a person must review." |
| 0:20 | Home | Tap the drop zone, pick the PDFs from Files; tap again and add the photo and the Excel file; untick one; tap Upload | "I can mix PDFs, photos, Excel and CSV, even from different places on the phone. Each file shows its type; I untick what I do not want, and upload the rest together." |
| 0:35 | Home | Point at the live steps and at `encrypted.pdf` | "Each file moves through upload, read, AI extract, check and done. A broken file fails alone with a clear code; the rest carry on." |
| 0:55 | Another tab | Open Search, show the floating dock | "The progress follows me to every screen. Model calls go through one client with a rate limiter, retries and a fallback model, so a busy model does not fail a document." |
| 1:15 | Home | Point at `payment_letter.pdf` | "A letter is not an invoice, so nothing is invented. The system says: no invoice found." |
| 1:25 | `bd_vat_invoice_0.pdf` | Open it, scroll the card | "A Bangladeshi VAT invoice: Tk, lakh grouping and the slash-dash ending. Every field has a confidence and the text it came from. The discount and the delivery charge are counted in the total check." |
| 1:50 | Same page | Tap View original | "I can compare with the original file." |
| 2:00 | Home, Needs attention | Open `planted_wrong_total.pdf` | "Here the total does not match subtotal plus tax. The model only reads; Python does the arithmetic and flags it." |
| 2:15 | Invoice card | Tap Fix, correct the total, save | "I correct it. The change is recorded with my name, the rules run again, and search updates." |
| 2:35 | `photo_upside_down.jpg` | Open it | "A phone photo taken upside down. OCR cleans it, flips it, and reads it." |
| 2:45 | Search | Type an invoice number, then "printer supplies", both in Best match | "Best match combines full-text search, for exact codes and names, with meaning search on pgvector, and merges the two rankings. One box handles both." |
| 3:00 | Home, document list | Tick two files, tap Compare these two; or tick several and Download marked for Excel | "I can mark several documents and act on them at once: process again, export, compare or delete." |
| 3:05 | Compare | Upload the reconciliation pair if not yet done, choose both | "PDF against Excel: matched, a changed total, a row with no number matched by supplier, date and total, and invoices on one side only." |
| 3:30 | Home | Tap Download invoices for Excel, show the stats line | "Everything exports to Excel. The line at the bottom shows the success rate, average time, tokens and what they cost at paid Gemini prices." |
| 3:45 | Browser: `/api/docs` | Scroll the endpoint list | "Every action is a REST endpoint: upload, status, results, search, corrections, reprocessing, export, stats." |
| 4:00 | GitHub: Actions | Show a green CI run and the Evaluation run | "Every push runs lint, 412 backend tests on Postgres, a secret scan and a Docker smoke test. The evaluation runs the whole pipeline with real Gemini on a labelled dataset." |
| 4:15 | GitHub: `docs/EVALUATION.md` | Show the results and cost tables | "Run 5: all eight fields correct on 91 of 91 invoices, every planted error caught, no failed documents, about $0.0015 per invoice at paid Gemini prices. The data is synthetic, so real accuracy will be lower; the report lists the weak spots." |
| 4:35 | GitHub: `DECISIONS.md` | Scroll | "Every design choice is written down with its alternatives and trade-off. Thank you." |

## If something goes wrong while recording

- A file stays on "queued": the worker may be waking with the server; wait 30 seconds.
- Semantic search says the model is busy: try again, or show keyword search only.
- Do not show the Render or Supabase dashboards: they hold keys.
