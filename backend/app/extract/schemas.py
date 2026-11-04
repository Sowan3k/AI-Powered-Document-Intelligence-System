"""Schemas for extraction.

Two layers:

1. `Llm*` models are what the model must return. Every value is the text as
   printed on the document, never a converted number or date, so the model
   only reads (CLAUDE.md AI rule 1). Each field carries a confidence and a
   short evidence snippet copied from the source. These models avoid
   `extra="forbid"`, because it becomes `additionalProperties` in the schema
   sent to Gemini, and unknown keys are dropped on parsing anyway.
2. `InvoiceData` is what code builds from that: dates as `date`, money as
   `Decimal`, currency as an ISO 4217 code, plus flags for anything doubtful.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)


class LlmField(BaseModel):
    value: str | None = Field(
        description="The value exactly as printed, or null if absent or unclear."
    )
    confidence: float = Field(ge=0, le=1, description="0 to 1. How sure the reading is.")
    evidence: str | None = Field(
        description="A short snippet copied exactly from the text that shows the value, or null."
    )

    @model_validator(mode="after")
    def _blank_is_null(self) -> "LlmField":
        if self.value is not None and not self.value.strip():
            self.value = None
        return self


class LlmLineItem(BaseModel):
    page: int = Field(ge=1, description="Page the line is printed on.")
    description: str | None
    quantity: str | None
    unit_price: str | None
    amount: str | None
    confidence: float = Field(ge=0, le=1)


class LlmInvoice(BaseModel):
    page_start: int = Field(ge=1, description="First page of this invoice.")
    page_end: int = Field(ge=1, description="Last page of this invoice.")
    invoice_number: LlmField
    invoice_date: LlmField
    supplier_name: LlmField
    customer_name: LlmField
    subtotal: LlmField
    tax: LlmField
    total: LlmField
    currency: LlmField = Field(description="Currency symbol or code as printed, e.g. $, EUR, Tk.")
    line_items: list[LlmLineItem]

    @model_validator(mode="after")
    def _page_order(self) -> "LlmInvoice":
        if self.page_end < self.page_start:
            raise ValueError("page_end must not be before page_start")
        return self


class LlmExtraction(BaseModel):
    invoices: list[LlmInvoice] = Field(
        description="Every invoice found, in page order. May be empty."
    )


class LlmColumnMapping(BaseModel):
    """For each invoice field, the sheet header that holds it, or null."""

    invoice_number: str | None
    invoice_date: str | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: str | None
    tax: str | None
    total: str | None
    currency: str | None
    description: str | None
    quantity: str | None
    unit_price: str | None
    amount: str | None


class FieldValue[T](BaseModel):
    value: T | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: str | None = None
    raw: str | None = None  # the text the value came from
    flags: list[str] = []  # e.g. evidence_not_found, unparsed, ambiguous_date


class LineItemData(BaseModel):
    position: int = Field(ge=1)
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class InvoiceData(BaseModel):
    """One normalised invoice, ready to store and validate."""

    page_start: int | None = None
    page_end: int | None = None
    sheet_index: int | None = None
    row_start: int | None = None
    row_end: int | None = None

    invoice_number: FieldValue[str] = FieldValue()
    invoice_date: FieldValue[date] = FieldValue()
    supplier_name: FieldValue[str] = FieldValue()
    customer_name: FieldValue[str] = FieldValue()
    subtotal: FieldValue[Decimal] = FieldValue()
    tax: FieldValue[Decimal] = FieldValue()
    total: FieldValue[Decimal] = FieldValue()
    currency: FieldValue[str] = FieldValue()
    line_items: list[LineItemData] = []
    # Currency codes seen anywhere in this invoice's values (R11 uses it).
    currencies_seen: list[str] = []

    def field(self, name: str) -> FieldValue:
        return getattr(self, name)
