"""Cross-verification of two documents (D16, D43)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.schemas import ReconcileRequest, ReconcileResponse
from app.core.config import Settings, get_settings
from app.db.models import Reconciliation
from app.db.session import get_db
from app.validate.reconcile import reconcile_documents

router = APIRouter(tags=["reconcile"], dependencies=[Depends(current_user)])


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
