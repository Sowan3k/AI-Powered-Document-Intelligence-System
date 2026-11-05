"""Cross-verification of two documents (D16, D43)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import current_user
from app.api.schemas import (
    PairDocument,
    PairSuggestion,
    PairSuggestions,
    ReconcileRequest,
    ReconcileResponse,
)
from app.core.config import Settings, get_settings
from app.db.enums import DocumentStatus, SourceKind
from app.db.models import Document, Invoice, Reconciliation
from app.db.session import get_db
from app.validate.reconcile import reconcile_documents

router = APIRouter(tags=["reconcile"], dependencies=[Depends(current_user)])

# Suggestions look at this many of the newest completed documents, so the
# self-join stays small however many documents the system holds.
SUGGESTION_WINDOW = 300
# A statement or scan reads naturally as side A, a register or export as side B.
KIND_ORDER = {SourceKind.PDF: 0, SourceKind.IMAGE: 1, SourceKind.SPREADSHEET: 2, SourceKind.CSV: 3}


@router.get("/reconcile/suggestions", response_model=PairSuggestions)
def suggest_pairs(
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
) -> PairSuggestions:
    """Pairs of completed documents that share invoices, most shared first (D72).

    Two invoices are the same one by the rules reconciliation uses: the same
    normalised number, or the same supplier, date and total.
    """
    recent = (
        select(Document.id)
        .where(Document.status == DocumentStatus.COMPLETED)
        .order_by(Document.created_at.desc())
        .limit(SUGGESTION_WINDOW)
        .scalar_subquery()
    )
    a, b = aliased(Invoice), aliased(Invoice)
    same_number = and_(
        a.invoice_number_norm.is_not(None),
        a.invoice_number_norm != "",
        a.invoice_number_norm == b.invoice_number_norm,
    )
    same_facts = and_(
        a.supplier_norm.is_not(None),
        a.supplier_norm == b.supplier_norm,
        a.invoice_date == b.invoice_date,
        a.total == b.total,
    )
    shared = func.count(func.distinct(a.id)).label("shared")
    rows = db.execute(
        select(a.document_id, b.document_id, shared)
        .select_from(a)
        .join(b, and_(a.document_id < b.document_id, or_(same_number, same_facts)))
        .where(a.document_id.in_(recent), b.document_id.in_(recent))
        .group_by(a.document_id, b.document_id)
        .order_by(shared.desc())
        .limit(limit)
    ).all()
    if not rows:
        return PairSuggestions(items=[])
    ids = {doc_id for row in rows for doc_id in row[:2]}
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(ids)))}
    counts = dict(
        db.execute(
            select(Invoice.document_id, func.count())
            .where(Invoice.document_id.in_(ids))
            .group_by(Invoice.document_id)
        ).all()
    )

    def brief(doc: Document) -> PairDocument:
        return PairDocument(
            id=doc.id,
            filename=doc.filename,
            source_kind=doc.source_kind,
            invoice_count=counts.get(doc.id, 0),
            created_at=doc.created_at,
        )

    def side_order(doc: Document) -> tuple[int, object]:
        return (KIND_ORDER.get(doc.source_kind, 9) if doc.source_kind else 9, doc.created_at)

    items = []
    for id_a, id_b, count in rows:
        first, second = sorted((docs[id_a], docs[id_b]), key=side_order)
        items.append(
            PairSuggestion(document_a=brief(first), document_b=brief(second), shared=count)
        )
    return PairSuggestions(items=items)


@router.post(
    "/reconcile",
    status_code=status.HTTP_201_CREATED,
    response_model=ReconcileResponse,
    responses={400: {}, 404: {}},
)
def reconcile(
    body: ReconcileRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReconcileResponse:
    if body.document_a == body.document_b:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "choose two different documents")
    try:
        row = reconcile_documents(db, body.document_a, body.document_b, settings)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return ReconcileResponse.model_validate(row)


@router.get("/reconciliations/{reconciliation_id}", response_model=ReconcileResponse)
def get_reconciliation(
    reconciliation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReconcileResponse:
    row = db.get(Reconciliation, reconciliation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reconciliation not found")
    return ReconcileResponse.model_validate(row)
