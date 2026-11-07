"""Reconciliation matching and comparison, without a database."""

from datetime import date
from decimal import Decimal

from app.validate.reconcile import Record, reconcile
from app.validate.similarity import similarity

D = Decimal


def rec(n: str | None, supplier: str = "Acme Traders Ltd", total: str = "100.00", **kw) -> Record:  # type: ignore[no-untyped-def]
    return Record(
        id=f"id-{n}-{supplier[:3]}",
        invoice_number=n,
        invoice_number_norm=n.replace("-", "") if n else None,
        invoice_date=kw.get("invoice_date", date(2026, 10, 1)),
        supplier_name=supplier,
        customer_name=kw.get("customer_name", "Riverside Clinic"),
        subtotal=kw.get("subtotal", D(total)),
        tax=kw.get("tax", D("0.00")),
        total=D(total),
        currency=kw.get("currency", "USD"),
        where="pages 1-1",
    )


def run(a: list[Record], b: list[Record]) -> dict:
    return reconcile(a, b, tolerance=D("0.01"), supplier_similarity=0.5)


def test_pg_trgm_style_similarity() -> None:
    assert similarity("acme traders", "acme traders") == 1.0
    assert similarity("acme traders", "acme tradres") > 0.5
    assert similarity("acme traders", "delta hardware") == 0.0
    assert similarity(None, "x") == 0.0


def test_all_four_outcomes() -> None:
    a = [rec("A-1"), rec("A-2", total="50.00"), rec("A-3"), rec("A-9", total="70.00",
         invoice_date=date(2026, 9, 9))]  # fmt: skip
    b = [rec("A-1"), rec("A-2", total="75.00"), rec(None, "ACME TRADERS LIMITED", "70.00",
         invoice_date=date(2026, 9, 9)), rec("B-5", total="999.00")]  # fmt: skip
    result = run(a, b)
    assert result["summary"] == {"invoices_a": 4, "invoices_b": 4, "matched": 2,
                                 "mismatched": 1, "only_in_a": 1, "only_in_b": 1}  # fmt: skip
    assert [(m["a"]["invoice_number"], m["matched_on"]) for m in result["matched"]] == [
        ("A-1", "invoice_number"),
        ("A-9", "supplier_date_total"),
    ]
    [mismatch] = result["mismatched"]
    diffs = {d["field"]: (d["a"], d["b"]) for d in mismatch["differences"]}
    assert diffs == {"subtotal": ("50.00", "75.00"), "total": ("50.00", "75.00")}
    assert [r["invoice_number"] for r in result["only_in_a"]] == ["A-3"]
    assert [r["invoice_number"] for r in result["only_in_b"]] == ["B-5"]


def test_number_formats_match_after_normalising() -> None:
    a = [rec("INV-2026-7")]
    b = [rec("INV-2026-7")]
    b[0].invoice_number = "inv 2026 7"
    assert run(a, b)["summary"]["matched"] == 1


def test_supplier_spelling_is_not_a_difference() -> None:
    result = run([rec("A-1")], [rec("A-1", "ACME TRADERS LIMITED")])
    assert result["summary"]["matched"] == 1


def test_fallback_needs_supplier_date_and_total() -> None:
    other_supplier = run([rec(None)], [rec(None, "Delta Hardware Co")])
    assert other_supplier["summary"]["matched"] == 0
    other_total = run([rec(None)], [rec(None, total="100.50")])
    assert other_total["summary"]["only_in_a"] == 1


def test_each_invoice_is_used_once() -> None:
    result = run([rec("A-1"), rec("A-1")], [rec("A-1")])
    assert result["summary"]["matched"] == 1 and result["summary"]["only_in_a"] == 1


def test_empty_documents() -> None:
    assert run([], [])["summary"]["matched"] == 0


def test_fallback_match_with_another_number_is_a_mismatch() -> None:
    # Same supplier, date and total; the number was misread on one side.
    result = run([rec("INV-0O7")], [rec("INV-007")])
    [pair] = result["mismatched"]
    assert pair["matched_on"] == "supplier_date_total"
    assert [d["field"] for d in pair["differences"]] == ["invoice_number"]


def test_a_shared_number_pairs_with_the_same_supplier() -> None:
    """Short numbers repeat across suppliers: the right row is the same supplier (D88)."""
    a = [rec("1001", "Padma Printing House")]
    b = [rec("1001", "Delta Hardware Co"), rec("1001", "Padma Printing House")]
    out = run(a, b)
    [pair] = out["matched"]
    assert pair["b"]["supplier_name"] == "Padma Printing House"
    assert [r["supplier_name"] for r in out["only_in_b"]] == ["Delta Hardware Co"]
