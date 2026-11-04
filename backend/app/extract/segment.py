"""Find invoices in a run of pages: overlapping windows, then merge across edges (D11).

Each window of SEGMENT_WINDOW_PAGES pages goes to the model in one call. The
last SEGMENT_OVERLAP_PAGES pages of a window open the next one, so an invoice
cut by a window edge is seen whole, or at least with its header, in one of
them. Results are merged:

- the same normalised invoice number in touching page ranges is one invoice;
- an invoice with no number that starts on a window's first page and touches
  the previous invoice's last page is that invoice's continuation.

Merging keeps the more confident value of each field, and takes line items
page by page so lines on a shared page are not counted twice.
"""

from collections.abc import Callable

from app.extract.normalise import norm_invoice_number
from app.extract.schemas import FIELDS, LlmExtraction, LlmInvoice


def windows(page_numbers: list[int], size: int, overlap: int) -> list[list[int]]:
    if not page_numbers:
        return []
    overlap = min(overlap, size - 1)
    step = size - overlap
    out = []
    start = 0
    while True:
        out.append(page_numbers[start : start + size])
        if start + size >= len(page_numbers):
            return out
        start += step


def page_range_check(window: list[int]) -> Callable[[LlmExtraction], None]:
    allowed = set(window)

    def check(result: LlmExtraction) -> None:
        for n, inv in enumerate(result.invoices):
            for page in (inv.page_start, inv.page_end, *(li.page for li in inv.line_items)):
                if page not in allowed:
                    raise ValueError(
                        f"invoices.{n}: page {page} is not one of the pages shown "
                        f"({window[0]} to {window[-1]})"
                    )

    return check


def _better(a, b):  # type: ignore[no-untyped-def]
    """Pick the field with a value and the higher confidence."""
    if a.value is None:
        return b
    if b.value is None:
        return a
    return b if b.confidence > a.confidence else a


def merge_pair(first: LlmInvoice, second: LlmInvoice) -> LlmInvoice:
    """Combine two views of one invoice. `second` starts on the same page or later."""
    fields = {name: _better(getattr(first, name), getattr(second, name)) for name in FIELDS}
    items = [li for li in first.line_items if li.page < second.page_start] + list(second.line_items)
    return LlmInvoice(
        page_start=min(first.page_start, second.page_start),
        page_end=max(first.page_end, second.page_end),
        line_items=items,
        **fields,
    )


def merge_windows(results: list[tuple[list[int], list[LlmInvoice]]]) -> list[LlmInvoice]:
    merged: list[LlmInvoice] = []
    for window, invoices in results:
        for inv in sorted(invoices, key=lambda i: (i.page_start, i.page_end)):
            key = norm_invoice_number(inv.invoice_number.value)
            target = None
            for i in range(len(merged) - 1, -1, -1):
                prev = merged[i]
                touches = inv.page_start <= prev.page_end + 1 and inv.page_end >= prev.page_start
                prev_key = norm_invoice_number(prev.invoice_number.value)
                if key and prev_key == key and touches:
                    target = i
                    break
                continuation = key is None and inv.page_start == window[0]
                if continuation and inv.page_start <= prev.page_end:
                    target = i
                    break
            if target is None:
                merged.append(inv)
            else:
                merged[target] = merge_pair(merged[target], inv)
    merged.sort(key=lambda i: (i.page_start, i.page_end))
    return merged
