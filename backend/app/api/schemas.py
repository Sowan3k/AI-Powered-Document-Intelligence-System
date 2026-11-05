"""Request and response models for the REST API. Money is sent as decimal strings."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    computed_field,
)

from app.db.enums import DocumentStatus, JobStatus, PageMethod, ReviewStatus, Severity, SourceKind

# Decimals go out as strings ("130.20"), so no client turns money into floats.
Money = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (a scheme name, not a secret)
    expires_in: int


class JobOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    job_type: str
    status: JobStatus
    attempts: int
    max_attempts: int
    progress_done: int
    progress_total: int | None
    last_error: str | None
    run_after: datetime
    created_at: datetime
    finished_at: datetime | None


class DocumentOut(ORM):
    id: uuid.UUID
    filename: str
    mime_type: str | None
    size_bytes: int
    page_count: int | None
    source_kind: SourceKind | None
    status: DocumentStatus
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    latest_job: JobOut | None = None
    invoice_count: int | None = None


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class EventOut(ORM):
    event: str
    job_id: uuid.UUID | None
    detail: dict[str, Any] | None
    created_at: datetime


class PageOut(ORM):
    page_number: int
    method: PageMethod
    ocr_confidence: float | None
    text: str


class DocumentDetail(DocumentOut):
    jobs: list[JobOut]
    history: list[EventOut]


class UploadResult(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus
    error_code: str | None
    error_message: str | None
    job_id: uuid.UUID | None


class UploadResponse(BaseModel):
    documents: list[UploadResult]
    accepted: int
    rejected: int


class LineItemOut(ORM):
    position: int
    description: str | None
    quantity: Money | None
    unit_price: Money | None
    amount: Money | None
    confidence: float | None


class IssueOut(ORM):
    rule_code: str
    severity: Severity
    field: str | None
    message: str
    details: dict[str, Any] | None
    created_at: datetime


class CorrectionOut(ORM):
    field: str
    old_value: Any
    new_value: Any
    username: str
    created_at: datetime


class AdjustmentOut(BaseModel):
    """A discount (negative), charge, extra duty or rounding line counted in the total."""

    label: str
    amount: Money | None
    flags: list[str] = []


class InvoiceOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    page_start: int | None
    page_end: int | None
    row_start: int | None
    row_end: int | None
    invoice_number: str | None
    invoice_date: date | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: Money | None
    tax: Money | None
    total: Money | None
    currency: str | None
    review_status: ReviewStatus
    field_meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def adjustments(self) -> list[AdjustmentOut]:
        return [
            AdjustmentOut(
                label=a.get("label") or "Adjustment",
                amount=a.get("amount"),
                flags=a.get("flags") or [],
            )  # fmt: skip
            for a in self.field_meta.get("adjustments") or []
        ]


class InvoiceDetail(InvoiceOut):
    line_items: list[LineItemOut]
    issues: list[IssueOut]
    corrections: list[CorrectionOut]


class ResultsResponse(BaseModel):
    document: DocumentOut
    invoices: list[InvoiceDetail]
    pages: list[PageOut] = []


class InvoicePatch(BaseModel):
    """Only the fields sent are changed. Send null to clear a field."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None
    ) = None
    invoice_date: date | None = None
    supplier_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None
    customer_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None
    subtotal: Annotated[Decimal, Field(max_digits=14, decimal_places=2)] | None = None
    tax: Annotated[Decimal, Field(max_digits=14, decimal_places=2)] | None = None
    total: Annotated[Decimal, Field(max_digits=14, decimal_places=2)] | None = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{3}$")] | None = None
    mark_reviewed: bool = False


class ReviewItem(InvoiceOut):
    filename: str
    error_count: int
    warning_count: int
    top_issue: str | None = None  # the first error, so a person can decide without opening it


class ReviewPage(BaseModel):
    items: list[ReviewItem]
    total: int
    limit: int
    offset: int


class SearchHit(InvoiceOut):
    filename: str
    score: float | None
    line_items: list[LineItemOut]


class SearchResponse(BaseModel):
    mode: Literal["keyword", "semantic", "hybrid"]
    query: str | None
    items: list[SearchHit]
    total: int
    limit: int
    offset: int


class ReconcileRequest(BaseModel):
    document_a: uuid.UUID
    document_b: uuid.UUID


class PairDocument(BaseModel):
    id: uuid.UUID
    filename: str
    source_kind: SourceKind | None
    invoice_count: int
    created_at: datetime


class PairSuggestion(BaseModel):
    document_a: PairDocument
    document_b: PairDocument
    shared: int  # invoices that appear in both, by number or by supplier, date and total


class PairSuggestions(BaseModel):
    items: list[PairSuggestion]


class ReconcileResponse(ORM):
    id: uuid.UUID
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    result: dict[str, Any]
    created_at: datetime
