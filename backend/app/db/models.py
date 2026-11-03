"""SQLAlchemy models for every table in the DocIntel data model.

Conventions (see DECISIONS.md D19 to D22):
- UUID keys for rows the API exposes by ID; BIGINT identity keys for child rows.
- Money is NUMERIC(14,2). Quantity and unit price are NUMERIC(14,4).
- Status columns are VARCHAR with CHECK constraints, not native enums.
- `invoices.search_vector` is filled by application code, not a generated column.
- `invoices.embedding` has the dimension from EMBED_DIM.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.enums import (
    DocumentStatus,
    JobStatus,
    PageMethod,
    ReviewStatus,
    Severity,
    SourceKind,
)

# Deterministic constraint names, so Alembic migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# pgvector's HNSW index supports at most 2,000 dimensions for the vector type.
HNSW_MAX_DIM = 2000
EMBED_DIM = get_settings().embed_dim

MONEY = Numeric(14, 2)
QUANTITY = Numeric(14, 4)


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR column with a CHECK constraint that stores the enum values."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _bigint_pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=False), primary_key=True)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    filename: Mapped[str] = mapped_column(Text, nullable=False)  # display only, never a path
    mime_type: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text)  # UUID-based key in the bucket
    page_count: Mapped[int | None] = mapped_column(Integer)
    source_kind: Mapped[SourceKind | None] = mapped_column(str_enum(SourceKind, "source_kind"))
    status: Mapped[DocumentStatus] = mapped_column(
        str_enum(DocumentStatus, "status"),
        nullable=False,
        default=DocumentStatus.QUEUED,
        server_default=DocumentStatus.QUEUED.value,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    sheets: Mapped[list["Sheet"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        Index("ix_documents_created_at", "created_at"),
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = _bigint_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    method: Mapped[PageMethod] = mapped_column(str_enum(PageMethod, "method"), nullable=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)  # 0 to 100, OCR pages only
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[Document] = relationship(back_populates="pages")

    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
    )


class Sheet(Base):
    __tablename__ = "sheets"

    id: Mapped[int] = _bigint_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based order in file
    sheet_name: Mapped[str] = mapped_column(Text, nullable=False)
    header_row: Mapped[int | None] = mapped_column(Integer)
    column_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[Document] = relationship(back_populates="sheets")

    __table_args__ = (UniqueConstraint("document_id", "sheet_index"),)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Where the invoice came from: a page range (PDF, image) or sheet rows.
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    sheet_id: Mapped[int | None] = mapped_column(
        ForeignKey("sheets.id", ondelete="CASCADE"), index=True
    )
    row_start: Mapped[int | None] = mapped_column(Integer)
    row_end: Mapped[int | None] = mapped_column(Integer)

    # The nine extracted fields (line items live in their own table).
    invoice_number: Mapped[str | None] = mapped_column(Text)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    supplier_name: Mapped[str | None] = mapped_column(Text)
    customer_name: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal | None] = mapped_column(MONEY)
    tax: Mapped[Decimal | None] = mapped_column(MONEY)
    total: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(3))  # ISO 4217 code

    # Normalised keys for duplicate checks (R06, R07) and reconciliation.
    invoice_number_norm: Mapped[str | None] = mapped_column(Text)
    supplier_norm: Mapped[str | None] = mapped_column(Text)

    # Per-field confidence and evidence: {"total": {"confidence": 0.9, "evidence": "..."}}
    field_meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # The schema-valid LLM output before normalisation, kept for audit and evaluation.
    raw_extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    review_status: Mapped[ReviewStatus] = mapped_column(
        str_enum(ReviewStatus, "review_status"),
        nullable=False,
        default=ReviewStatus.PENDING,
        server_default=ReviewStatus.PENDING.value,
        index=True,
    )
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    document: Mapped[Document] = relationship(back_populates="invoices")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LineItem.position",
    )
    issues: Mapped[list["ValidationIssue"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True
    )
    corrections: Mapped[list["Correction"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "page_start IS NULL OR page_end IS NULL OR page_end >= page_start",
            name="page_range",
        ),
        CheckConstraint(
            "row_start IS NULL OR row_end IS NULL OR row_end >= row_start", name="row_range"
        ),
        Index("ix_invoices_supplier_number", "supplier_norm", "invoice_number_norm"),
        Index("ix_invoices_invoice_date", "invoice_date"),
        Index("ix_invoices_search_vector", "search_vector", postgresql_using="gin"),
        *(
            [
                Index(
                    "ix_invoices_embedding_hnsw",
                    "embedding",
                    postgresql_using="hnsw",
                    postgresql_ops={"embedding": "vector_cosine_ops"},
                )
            ]
            if EMBED_DIM <= HNSW_MAX_DIM
            else []
        ),
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = _bigint_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # order on the invoice
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(QUANTITY)
    unit_price: Mapped[Decimal | None] = mapped_column(QUANTITY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    confidence: Mapped[float | None] = mapped_column(Float)

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")

    __table_args__ = (UniqueConstraint("invoice_id", "position"),)


class ValidationIssue(Base):
    __tablename__ = "validation_issues"

    id: Mapped[int] = _bigint_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_code: Mapped[str] = mapped_column(String(10), nullable=False)  # R01 to R11
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity"), nullable=False)
    field: Mapped[str | None] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    invoice: Mapped[Invoice] = relationship(back_populates="issues")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[int] = _bigint_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    invoice: Mapped[Invoice] = relationship(back_populates="corrections")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "status"),
        nullable=False,
        default=JobStatus.QUEUED,
        server_default=JobStatus.QUEUED.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))  # worker id
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    progress_done: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    progress_total: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    document: Mapped[Document] = relationship(back_populates="jobs")

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        # The worker claims the oldest runnable queued job with FOR UPDATE SKIP LOCKED.
        Index("ix_jobs_claim", "status", "run_after"),
    )


class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = _bigint_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_processing_events_document_time", "document_id", "created_at"),)


class Reconciliation(Base):
    __tablename__ = "reconciliations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created_at()
