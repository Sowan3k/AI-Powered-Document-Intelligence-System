"""Windows over pages, and merging invoices across window edges."""

import pytest

from app.core.config import Settings
from app.extract.llm import LlmOutputError
from app.extract.schemas import LlmInvoice
from app.extract.segment import merge_windows, windows
from app.extract.service import extract_pages
from tests.conftest import FakeCall, FakeLlmClient
from tests.unit.extract.helpers import line, llm_invoice


def inv(**kw) -> LlmInvoice:  # type: ignore[no-untyped-def]
    return LlmInvoice.model_validate(llm_invoice(**kw))


def test_windows_overlap() -> None:
    assert windows(list(range(1, 11)), 4, 1) == [[1, 2, 3, 4], [4, 5, 6, 7], [7, 8, 9, 10]]
    assert windows([1, 2, 3], 8, 1) == [[1, 2, 3]]
    assert windows(list(range(1, 6)), 2, 0) == [[1, 2], [3, 4], [5]]
    assert windows([], 4, 1) == []
    assert windows([1, 2, 3], 1, 5) == [[1], [2], [3]]  # overlap never stalls the walk


def test_same_number_across_the_edge_is_one_invoice() -> None:
    a = inv(page_start=3, page_end=4, invoice_number="A-1", total=None,
            items=[line(3, "x", "1", "1", "1.00"), line(4, "y", "1", "2", "2.00")])  # fmt: skip
    b = inv(page_start=4, page_end=5, invoice_number="A-1", total="9.00",
            items=[line(4, "y", "1", "2", "2.00"), line(5, "z", "1", "6", "6.00")])  # fmt: skip
    [merged] = merge_windows([([1, 2, 3, 4], [a]), ([4, 5, 6, 7], [b])])
    assert (merged.page_start, merged.page_end) == (3, 5)
    assert merged.total.value == "9.00"
    # The line on shared page 4 is counted once.
    assert [li.description for li in merged.line_items] == ["x", "y", "z"]


def test_continuation_without_number_joins_the_previous_invoice() -> None:
    a = inv(page_start=3, page_end=4, invoice_number="A-1")
    b = inv(page_start=4, page_end=5, invoice_number=None, total="9.00")
    [merged] = merge_windows([([1, 2, 3, 4], [a]), ([4, 5, 6, 7], [b])])
    assert merged.invoice_number.value == "A-1" and merged.total.value == "9.00"


def test_different_invoices_stay_apart() -> None:
    a = inv(page_start=4, page_end=4, invoice_number="A-1")
    b = inv(page_start=4, page_end=4, invoice_number="B-2")
    c = inv(page_start=6, page_end=6, invoice_number="A-1")  # same number, far away
    merged = merge_windows([([1, 2, 3, 4], [a]), ([4, 5, 6, 7], [b, c])])
    assert [(m.invoice_number.value, m.page_start) for m in merged] == [
        ("A-1", 4),
        ("B-2", 4),
        ("A-1", 6),
    ]


def test_higher_confidence_wins() -> None:
    weak = {"value": "1.00", "confidence": 0.3, "evidence": "1.00"}
    strong = {"value": "7.00", "confidence": 0.95, "evidence": "7.00"}
    a = inv(page_start=4, invoice_number="A-1", total=weak)
    b = inv(page_start=4, invoice_number="A-1", total=strong)
    [merged] = merge_windows([([1, 2, 3, 4], [a]), ([4, 5], [b])])
    assert merged.total.value == "7.00"


def pages(n: int) -> list[tuple[int, str]]:
    return [(i, f"Invoice INV-{i} total {i}.00") for i in range(1, n + 1)]


def window_of(call: FakeCall) -> list[int]:
    text = call.turns[0].parts[0]
    return [int(x.split(" ---")[0]) for x in text.split("--- page ")[1:]]


def test_extract_pages_calls_once_per_window_and_merges() -> None:
    def reply(call: FakeCall) -> dict:
        found = [llm_invoice(n, invoice_number=f"INV-{n}") for n in window_of(call)]
        return {"invoices": found}

    fake = FakeLlmClient(reply)
    settings = Settings(segment_window_pages=4, segment_overlap_pages=1)
    found, usages = extract_pages(fake, "m", pages(10), settings)
    assert len(fake.calls) == 3 and len(usages) == 3
    assert [i.invoice_number.value for i in found] == [f"INV-{n}" for n in range(1, 11)]


def test_page_outside_the_window_is_rejected_and_retried() -> None:
    bad = {"invoices": [llm_invoice(9, invoice_number="INV-9")]}
    good = {"invoices": [llm_invoice(2, invoice_number="INV-2")]}
    fake = FakeLlmClient([bad, good])
    found, _ = extract_pages(fake, "m", pages(3), Settings())
    assert [i.page_start for i in found] == [2]
    assert "page 9 is not one of the pages shown" in fake.calls[1].turns[2].parts[0]


def test_blank_windows_make_no_call() -> None:
    fake = FakeLlmClient([])
    found, usages = extract_pages(fake, "m", [(1, ""), (2, "  \n")], Settings())
    assert found == [] and usages == [] and fake.calls == []


def test_two_bad_replies_raise() -> None:
    fake = FakeLlmClient(["{}", "[]"])
    with pytest.raises(LlmOutputError):
        extract_pages(fake, "m", pages(2), Settings())
