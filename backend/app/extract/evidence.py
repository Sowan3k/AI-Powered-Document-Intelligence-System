"""Check that each value the model returned really appears in the source text.

A value counts as proven when its evidence snippet appears in the source and
the value appears in the snippet. Comparison ignores case and runs of spaces,
since OCR text and model output differ there. Unproven values keep their
value but lose half their confidence and get the flag `evidence_not_found`,
which validation rule R10 turns into a review item (AI rule 3).
"""

import re
from decimal import Decimal

from app.extract.normalise import parse_amount
from app.extract.schemas import LlmField

FLAG = "evidence_not_found"
PENALTY = 0.5
_AMOUNT_TOKEN = re.compile(r"[\d][\d.,\s]*\d|\d")


def squash(text: str) -> str:
    return " ".join(text.lower().split())


def _amount_in(snippet: str, value: Decimal) -> bool:
    return any(parse_amount(tok) == value for tok in _AMOUNT_TOKEN.findall(snippet))


def is_proven(field: LlmField, source: str, *, amount: bool = False) -> bool:
    if field.value is None:
        return True  # nothing claimed, nothing to prove
    if not field.evidence:
        return False
    evidence, src, value = squash(field.evidence), squash(source), squash(field.value)
    if evidence not in src:
        return False
    if value in evidence:
        return True
    if amount:
        parsed = parse_amount(field.value)
        return parsed is not None and _amount_in(field.evidence, parsed)
    return False
