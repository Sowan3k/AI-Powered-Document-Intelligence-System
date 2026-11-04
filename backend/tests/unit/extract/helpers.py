"""Build model replies for tests."""

from app.extract.schemas import FIELDS


def fld(value: str | None, evidence: str | None = "", confidence: float = 0.9) -> dict:
    if evidence == "":
        evidence = value
    return {"value": value, "confidence": confidence, "evidence": evidence}


def llm_invoice(
    page_start: int = 1, page_end: int | None = None, items=None, adjustments=None, **values
) -> dict:  # type: ignore[no-untyped-def]
    """values: field name -> printed string, or a dict from fld(). Unset fields are null."""
    out: dict = {"page_start": page_start, "page_end": page_end or page_start}
    for name in FIELDS:
        v = values.get(name)
        out[name] = v if isinstance(v, dict) else fld(v, v if v is not None else None)
    out["line_items"] = items or []
    out["adjustments"] = adjustments or []
    return out


def line(page: int, description: str, qty: str, price: str, amount: str) -> dict:
    return {
        "page": page,
        "description": description,
        "quantity": qty,
        "unit_price": price,
        "amount": amount,
        "confidence": 0.9,
    }
