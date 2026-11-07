# Assignment brief

Source: "Ai Engineer Task 1.3.pdf", received from Care Guide on 3 November 2026. Submission within five days, by Reply All to the original email.

## AI Engineer

**Project:** AI-Powered Document Intelligence System
**Submission deadline:** 5 days

## Scenario

A company receives thousands of business documents daily, financial data including invoices, receipts, scanned PDFs, images, Excel spreadsheets, and CSV files (PDF pages are approx. 1000 pages). Employees manually extract invoice details, verify financial calculations, and enter the information into internal systems, PDF-PDF cross verification, PDF-Excel cross verification. This process is time-consuming and prone to errors. The company wants an AI-powered document intelligence system that automates document processing, extracts structured information, validates results, and makes the data searchable through an API and web interface.

## Assignment

**Task 1: Document Processing.** Design and implement a system that accepts multiple PDF, JPG, PNG, TIFF, XLSX, XLS, and CSV files. Extract text from digital PDFs, use OCR for scanned documents and images, and parse structured spreadsheet data. Handle multi-page PDFs, multiple sheets, poor image quality, and corrupted files.

**Task 2: AI Information Extraction.** Extract invoice number, invoice date, supplier name, customer name, subtotal, tax, total, currency, and line items. Return structured JSON and handle missing or uncertain information without inventing values.

**Task 3: Data Validation.** Implement validation rules to identify missing fields, incorrect numeric values, duplicate invoices, and inconsistencies between subtotal, tax, line items, and total amount. Flag records requiring manual review.

**Task 4: Backend API.** Build REST APIs for document uploads, processing status, extracted results, document search, manual corrections, and failed-job reprocessing. Use background processing for time-consuming OCR and AI operations.

**Task 5: Database and Search.** Design a database to store document metadata, extracted text, structured results, validation errors, and processing history. Implement keyword-based filtering and semantic search.

**Task 6: Frontend.** Build a simple React or Next.js interface where users can upload multiple documents, monitor processing progress, inspect extracted information, review validation errors, correct values, and search previously processed documents.

**Task 7: Testing and Evaluation.** Write automated tests for document processing, OCR, spreadsheet parsing, AI extraction, validation, API endpoints, and failure scenarios. Evaluate the system using a labeled dataset and report actual extraction accuracy, processing time, document success rate, and failure rate.

## Technology requirements

Suggested technologies include React/Next.js, Node.js/NestJS, Python-based OCR tools, pandas/openpyxl, an LLM API, PostgreSQL or MongoDB, Redis/BullMQ, and a vector database. Candidates may choose alternatives and explain their design decisions.

## Deliverables

1. Git repository containing the source code.
2. README and setup instructions.
3. Architecture diagram and database schema.
4. Working backend API and frontend.
5. PDF, image, Excel, and CSV processing pipelines.
6. Automated tests and test results.
7. Evaluation report with actual measured metrics.
8. Recorded walkthrough of the working application.
9. AI prompts and disclosure of AI-assisted development, where applicable.

The candidate should ensure smooth performance, high speed, scalability, reliability, and strong security.
