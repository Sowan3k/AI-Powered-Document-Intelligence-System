"""Trigram similarity, computed the way pg_trgm computes it (D30).

The database uses pg_trgm's `similarity()` for duplicate checks. Reconciliation
compares two documents already in memory, so it uses this copy of the same
formula: words are lower-cased, padded with two spaces before and one after,
cut into three-letter chunks, and the score is shared chunks over all chunks.
"""

import re


def trigrams(text: str) -> set[str]:
    out: set[str] = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        padded = f"  {word} "
        out.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return out


def similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
