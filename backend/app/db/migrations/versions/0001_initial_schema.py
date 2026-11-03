"""Initial schema: every table in the DocIntel data model.

Revision ID: 0001
Revises:
Create Date: 2026-11-03

The embedding column size comes from EMBED_DIM at the time this migration
runs. Changing EMBED_DIM later needs a new migration (DECISIONS.md D18).
Status columns are VARCHAR with CHECK constraints (D19). The values are
written out here, not imported, so this migration never changes after it ships.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HNSW_MAX_DIM = 2000


def _status(column: str, table: str, values: list[str], **kwargs: object) -> list[object]:
    """A VARCHAR(20) column plus the CHECK constraint that limits its values."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return [
        sa.Column(column, sa.String(20), **kwargs),
        sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_{table}_{column}")),
    ]


def _timestamps(updated: bool = True) -> list[sa.Column]:
    cols = [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]
    if updated:
        cols.append(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
    return cols


def _jsonb(name: str, *, nullable: bool, empty_default: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(),
        nullable=nullable,
        server_default=sa.text("'{}'::jsonb") if empty_default else None,
    )


def _bigint_id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True)


def _uuid_id() -> sa.Column:
    return sa.Column("id", sa.UUID(), primary_key=True)


def upgrade() -> None:
    embed_dim = get_settings().embed_dim

    # Supabase may already have the extension in its "extensions" schema.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        _uuid_id(),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text()),
        sa.Column("page_count", sa.Integer()),
        *_status("source_kind", "documents", ["pdf", "image", "spreadsheet", "csv"]),
        *_status(
            "status",
            "documents",
            ["queued", "processing", "completed", "failed"],
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.Text()),
        *_timestamps(),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_documents_size_non_negative")),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])

    op.create_table(
        "pages",
        _bigint_id(),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        *_status("method", "pages", ["digital", "ocr", "vision"], nullable=False),
        sa.Column("ocr_confidence", sa.Float()),
        *_timestamps(updated=False),
        sa.PrimaryKeyConstraint("id", name="pk_pages"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_pages_document_id_documents",
        ),
        sa.UniqueConstraint("document_id", "page_number", name="uq_pages_document_id_page_number"),
        sa.CheckConstraint("page_number >= 1", name=op.f("ck_pages_page_number_positive")),
    )

    op.create_table(
        "sheets",
        _bigint_id(),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.Text(), nullable=False),
        sa.Column("header_row", sa.Integer()),
        _jsonb("column_mapping", nullable=False, empty_default=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(updated=False),
        sa.PrimaryKeyConstraint("id", name="pk_sheets"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_sheets_document_id_documents",
        ),
        sa.UniqueConstraint("document_id", "sheet_index", name="uq_sheets_document_id_sheet_index"),
    )

    op.create_table(
        "invoices",
        _uuid_id(),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("sheet_id", sa.BigInteger()),
        sa.Column("row_start", sa.Integer()),
        sa.Column("row_end", sa.Integer()),
        sa.Column("invoice_number", sa.Text()),
        sa.Column("invoice_date", sa.Date()),
        sa.Column("supplier_name", sa.Text()),
        sa.Column("customer_name", sa.Text()),
        sa.Column("subtotal", sa.Numeric(14, 2)),
        sa.Column("tax", sa.Numeric(14, 2)),
        sa.Column("total", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("invoice_number_norm", sa.Text()),
        sa.Column("supplier_norm", sa.Text()),
        _jsonb("field_meta", nullable=False, empty_default=True),
        _jsonb("raw_extraction", nullable=True),
        *_status(
            "review_status",
            "invoices",
            ["pending", "ok", "needs_review", "reviewed"],
            nullable=False,
            server_default="pending",
        ),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        sa.Column("embedding", Vector(embed_dim)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_invoices_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["sheet_id"], ["sheets.id"], ondelete="CASCADE", name="fk_invoices_sheet_id_sheets"
        ),
        sa.CheckConstraint(
            "page_start IS NULL OR page_end IS NULL OR page_end >= page_start",
            name=op.f("ck_invoices_page_range"),
        ),
        sa.CheckConstraint(
            "row_start IS NULL OR row_end IS NULL OR row_end >= row_start",
            name=op.f("ck_invoices_row_range"),
        ),
    )
    op.create_index("ix_invoices_document_id", "invoices", ["document_id"])
    op.create_index("ix_invoices_sheet_id", "invoices", ["sheet_id"])
    op.create_index("ix_invoices_review_status", "invoices", ["review_status"])
    op.create_index("ix_invoices_invoice_date", "invoices", ["invoice_date"])
    op.create_index(
        "ix_invoices_supplier_number", "invoices", ["supplier_norm", "invoice_number_norm"]
    )
    op.create_index(
        "ix_invoices_search_vector", "invoices", ["search_vector"], postgresql_using="gin"
    )
    if embed_dim <= HNSW_MAX_DIM:
        op.create_index(
            "ix_invoices_embedding_hnsw",
            "invoices",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )

    op.create_table(
        "line_items",
        _bigint_id(),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("quantity", sa.Numeric(14, 4)),
        sa.Column("unit_price", sa.Numeric(14, 4)),
        sa.Column("amount", sa.Numeric(14, 2)),
        sa.Column("confidence", sa.Float()),
        sa.PrimaryKeyConstraint("id", name="pk_line_items"),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            ondelete="CASCADE",
            name="fk_line_items_invoice_id_invoices",
        ),
        sa.UniqueConstraint("invoice_id", "position", name="uq_line_items_invoice_id_position"),
    )

    op.create_table(
        "validation_issues",
        _bigint_id(),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("rule_code", sa.String(10), nullable=False),
        *_status("severity", "validation_issues", ["error", "warning", "info"], nullable=False),
        sa.Column("field", sa.String(50)),
        sa.Column("message", sa.Text(), nullable=False),
        _jsonb("details", nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_timestamps(updated=False),
        sa.PrimaryKeyConstraint("id", name="pk_validation_issues"),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            ondelete="CASCADE",
            name="fk_validation_issues_invoice_id_invoices",
        ),
    )
    op.create_index("ix_validation_issues_invoice_id", "validation_issues", ["invoice_id"])

    op.create_table(
        "corrections",
        _bigint_id(),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        _jsonb("old_value", nullable=True),
        _jsonb("new_value", nullable=True),
        sa.Column("username", sa.String(100), nullable=False),
        *_timestamps(updated=False),
        sa.PrimaryKeyConstraint("id", name="pk_corrections"),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            ondelete="CASCADE",
            name="fk_corrections_invoice_id_invoices",
        ),
    )
    op.create_index("ix_corrections_invoice_id", "corrections", ["invoice_id"])

    op.create_table(
        "jobs",
        _uuid_id(),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        *_status(
            "status",
            "jobs",
            ["queued", "running", "succeeded", "failed"],
            nullable=False,
            server_default="queued",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.String(100)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("progress_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_jobs_document_id_documents",
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts_non_negative")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_jobs_max_attempts_positive")),
    )
    op.create_index("ix_jobs_document_id", "jobs", ["document_id"])
    op.create_index("ix_jobs_claim", "jobs", ["status", "run_after"])

    op.create_table(
        "processing_events",
        _bigint_id(),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID()),
        sa.Column("event", sa.String(50), nullable=False),
        _jsonb("detail", nullable=True),
        *_timestamps(updated=False),
        sa.PrimaryKeyConstraint("id", name="pk_processing_events"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_processing_events_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], ondelete="SET NULL", name="fk_processing_events_job_id_jobs"
        ),
    )
    op.create_index(
        "ix_processing_events_document_time", "processing_events", ["document_id", "created_at"]
    )
    op.create_index("ix_processing_events_job_id", "processing_events", ["job_id"])

    op.create_table(
        "reconciliations",
        _uuid_id(),
        sa.Column("document_a_id", sa.UUID(), nullable=False),
        sa.Column("document_b_id", sa.UUID(), nullable=False),
        _jsonb("result", nullable=False),
        *_timestamps(updated=False),
        sa.PrimaryKeyConstraint("id", name="pk_reconciliations"),
        sa.ForeignKeyConstraint(
            ["document_a_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_reconciliations_document_a_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_b_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_reconciliations_document_b_id_documents",
        ),
    )
    op.create_index("ix_reconciliations_document_a_id", "reconciliations", ["document_a_id"])
    op.create_index("ix_reconciliations_document_b_id", "reconciliations", ["document_b_id"])


def downgrade() -> None:
    # Dropping a table drops its indexes and constraints. The vector extension
    # stays, because Supabase manages it.
    for table in (
        "reconciliations",
        "processing_events",
        "jobs",
        "corrections",
        "validation_issues",
        "line_items",
        "invoices",
        "sheets",
        "pages",
        "documents",
    ):
        op.drop_table(table)
