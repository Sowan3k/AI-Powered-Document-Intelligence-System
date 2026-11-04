# Database schema

PostgreSQL 17 with the `vector` (pgvector) and `pg_trgm` extensions. One hand-written Alembic migration creates everything (`backend/app/db/migrations/versions/0001_initial_schema.py`), and CI checks that the models and the migration match (`alembic check`).

Rules that apply to every table:

- Rows the API exposes by ID (documents, invoices, jobs, reconciliations) use random UUID keys. Child rows use BIGINT identity keys (D21).
- Money is `NUMERIC(14,2)`; quantity and unit price are `NUMERIC(14,4)` (D22). No column uses floats for money.
- Status columns are VARCHAR with CHECK constraints, mirrored by Python `StrEnum`s (D20).
- Deleting a document deletes everything that belongs to it.

```mermaid
erDiagram
    documents ||--o{ pages : "has"
    documents ||--o{ sheets : "has"
    documents ||--o{ invoices : "has"
    documents ||--o{ jobs : "has"
    documents ||--o{ processing_events : "history"
    jobs ||--o{ processing_events : "writes"
    sheets ||--o{ invoices : "rows of"
    invoices ||--o{ line_items : "has"
    invoices ||--o{ validation_issues : "has"
    invoices ||--o{ corrections : "has"
    documents ||--o{ reconciliations : "as A or B"

    documents {
        uuid id PK
        text filename "display only"
        varchar sha256
        bigint size_bytes
        text storage_path "uuid key"
        int page_count
        varchar source_kind "pdf, image, spreadsheet, csv"
        varchar status "queued, processing, completed, failed"
        varchar error_code
        text error_message
    }
    pages {
        bigint id PK
        uuid document_id FK
        int page_number
        text text
        varchar method "digital, ocr, vision"
        float ocr_confidence
    }
    sheets {
        bigint id PK
        uuid document_id FK
        int sheet_index
        text sheet_name
        int header_row
        jsonb column_mapping
        int row_count
    }
    invoices {
        uuid id PK
        uuid document_id FK
        int page_start
        int page_end
        bigint sheet_id FK
        int row_start
        int row_end
        text invoice_number
        date invoice_date
        text supplier_name
        text customer_name
        numeric subtotal "14,2"
        numeric tax "14,2"
        numeric total "14,2"
        varchar currency "ISO 4217"
        text invoice_number_norm
        text supplier_norm "pg_trgm index"
        jsonb field_meta "confidence, evidence, flags"
        jsonb raw_extraction
        varchar review_status "pending, ok, needs_review, reviewed"
        tsvector search_vector "GIN index"
        vector embedding "768, HNSW cosine"
    }
    line_items {
        bigint id PK
        uuid invoice_id FK
        int position
        text description
        numeric quantity "14,4"
        numeric unit_price "14,4"
        numeric amount "14,2"
        float confidence
    }
    validation_issues {
        bigint id PK
        uuid invoice_id FK
        varchar rule_code "R01 to R11"
        varchar severity "error, warning, info"
        varchar field
        text message
        jsonb details
        bool resolved
    }
    corrections {
        bigint id PK
        uuid invoice_id FK
        varchar field
        jsonb old_value
        jsonb new_value
        varchar username
    }
    jobs {
        uuid id PK
        uuid document_id FK
        varchar job_type "process, index"
        varchar status "queued, running, succeeded, failed"
        int attempts
        int max_attempts
        timestamptz run_after
        varchar locked_by
        timestamptz heartbeat_at
        text last_error
        int progress_done
        int progress_total
    }
    processing_events {
        bigint id PK
        uuid document_id FK
        uuid job_id FK
        varchar event
        jsonb detail
    }
    reconciliations {
        uuid id PK
        uuid document_a_id FK
        uuid document_b_id FK
        jsonb result
    }
```

## Indexes that matter

| Index | Serves |
|---|---|
| `ix_jobs_claim (status, run_after)` | The worker's claim query with `FOR UPDATE SKIP LOCKED` |
| `ix_invoices_supplier_number (supplier_norm, invoice_number_norm)` | Duplicate rule R06 |
| `ix_invoices_invoice_date` | Duplicate rule R07 and date filters |
| `ix_invoices_supplier_norm_trgm` (GIN, `gin_trgm_ops`) | Fuzzy supplier matching (D30, D42) |
| `ix_invoices_search_vector` (GIN) | Keyword search |
| `ix_invoices_embedding_hnsw` (HNSW, cosine) | Semantic search (D19) |
| `ix_processing_events_document_time` | A document's history in order |

## Why some data is JSON

`field_meta`, `raw_extraction`, `column_mapping`, issue `details` and the reconciliation `result` change shape with the document or the rule. JSONB keeps the strict columns strict (values the rules and search use) and the descriptive data flexible (D06).
