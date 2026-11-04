"""Turn printed text into typed values: Decimal amounts, ISO dates, ISO currency codes.

Nothing here guesses. Text that does not parse cleanly gives None, and the
caller flags the field for review.
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Bengali digits (U+09E6 to U+09EF) become ASCII before any parsing.
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

CURRENCY_CODES = {
    "USD", "EUR", "GBP", "BDT", "INR", "JPY", "CNY", "AUD", "CAD", "SGD", "MYR", "AED",
    "SAR", "CHF", "PKR", "LKR", "NPR", "THB", "IDR", "HKD", "NZD", "SEK", "NOK", "DKK",
}  # fmt: skip
# Symbols and words that name one currency without doubt in this product's market.
CURRENCY_SIGNS = {
    "$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "৳": "BDT", "TK": "BDT", "TAKA": "BDT",
    "₹": "INR", "RS": "INR", "¥": "JPY", "RM": "MYR", "S$": "SGD", "A$": "AUD", "C$": "CAD",
    "EURO": "EUR", "EUROS": "EUR", "DOLLAR": "USD", "DOLLARS": "USD", "টাকা": "BDT",
}  # fmt: skip
# "টাকা" (taka) sits with the symbols: Bengali vowel signs are not word
# characters, so a \b after it would never match.
_SIGN_PATTERN = re.compile(
    r"(US\$|S\$|A\$|C\$|টাকা|[$€£৳₹¥])|\b("
    + "|".join(sorted(CURRENCY_CODES))
    + r"|TK|TAKA|RS|RM|EUROS?|DOLLARS?)\b\.?",
    re.IGNORECASE,
)

MONTHS = {
    m: i
    for i, names in enumerate(
        [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
         ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
         ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
         ("dec", "december")],
        start=1,
    )
    for m in names
}  # fmt: skip
# Month names as printed on Bengali invoices, with the common spellings.
MONTHS.update(
    {
        unicodedata.normalize("NFC", m): i
        for i, names in enumerate(
            [("জানুয়ারি", "জানুয়ারী"), ("ফেব্রুয়ারি", "ফেব্রুয়ারী"), ("মার্চ",),
             ("এপ্রিল",), ("মে",), ("জুন",), ("জুলাই",), ("আগস্ট", "আগষ্ট"),
             ("সেপ্টেম্বর",), ("অক্টোবর",), ("নভেম্বর",), ("ডিসেম্বর",)],
            start=1,
        )
        for m in names
    }
)  # fmt: skip
_MONTH_WORD = r"[A-Za-z\u0980-\u09FF]+"


def ascii_digits(text: str) -> str:
    """Bengali digits to ASCII, and one Unicode form, so "১২" and "12" parse alike."""
    return unicodedata.normalize("NFC", text).translate(_BENGALI_DIGITS)


def currencies_in(text: str | None) -> list[str]:
    """Every currency named in the text, as ISO codes, in order, without repeats."""
    if not text:
        return []
    found: list[str] = []
    for symbol, word in _SIGN_PATTERN.findall(text):
        token = (symbol or word).upper()
        code = token if token in CURRENCY_CODES else CURRENCY_SIGNS.get(token)
        if code and code not in found:
            found.append(code)
    return found


def parse_currency(text: str | None) -> str | None:
    found = currencies_in(text)
    return found[0] if len(found) == 1 else None


def parse_amount(text: str | None) -> Decimal | None:
    """Parse a printed amount: "$1,234.50", "1.234,50 EUR", "(12.00)", "Tk. 1 234,50".

    The last separator is the decimal mark when both "," and "." appear. A
    single "," followed by three digits is a thousands mark ("1,234"), unless
    the whole part is 0 ("0,125"). Digit groups must be well formed, or the
    result is None. Lakh grouping ("1,23,456.00"), Bengali digits and the
    "/-" or "/=" ending used in Bangladesh ("Tk 5,000/-") are accepted.
    """
    if text is None:
        return None
    s = re.sub(r"\s*/[-=]\s*$", "", ascii_digits(text).strip())
    trailing_minus = s.endswith("-") and not s.endswith((",-", ".-"))  # "450,-" means 450
    negative = (s.startswith("(") and s.endswith(")")) or s.startswith("-") or trailing_minus
    s = _SIGN_PATTERN.sub(" ", s)
    s = re.sub(r"[\s\u00a0'()+-]", "", s)
    s = s.rstrip(",.")  # "450,-" and "450." end with a bare mark
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    commas, dots = s.count(","), s.count(".")
    if commas and dots:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
    elif commas + dots == 0:
        decimal = None
    elif commas > 1 or dots > 1:
        decimal = None  # "1,234,567" or "1.234.567"
    elif commas == 1:
        head, tail = s.split(",")
        decimal = None if len(tail) == 3 and head != "0" else ","
    else:
        decimal = "."
    thousands = {",": ".", ".": ","}.get(decimal or "", "," if commas else ".")
    whole, _, fraction = s.partition(decimal) if decimal else (s, "", "")
    if decimal and (not fraction.isdigit() or thousands in fraction):
        return None
    groups = whole.split(thousands)
    if len(groups) > 1 and not _well_grouped(groups, thousands):
        return None
    try:
        value = Decimal("".join(groups) + ("." + fraction if fraction else ""))
    except InvalidOperation:
        return None
    return -value if negative else value


def _well_grouped(groups: list[str], mark: str) -> bool:
    """Thousands ("1,234,567") or, with commas, lakh grouping ("12,34,567")."""
    if 1 <= len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:]):
        return True
    return (
        mark == ","
        and len(groups) > 2
        and 1 <= len(groups[0]) <= 2
        and all(len(g) == 2 for g in groups[1:-1])
        and len(groups[-1]) == 3
    )


def parse_quantity(text: str | None) -> Decimal | None:
    return parse_amount(text)


def parse_date(text: str | None, day_first: bool = True) -> tuple[date | None, bool]:
    """Return (date, ambiguous). Ambiguous means day and month could swap."""
    if not text:
        return None, False
    s = " ".join(ascii_digits(text).strip().replace(",", " ").split()).rstrip(".")
    iso = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ].*)?", s)
    if iso:
        return _make(int(iso[1]), int(iso[2]), int(iso[3])), False
    numeric = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})", s)
    if numeric:
        a, b, year = int(numeric[1]), int(numeric[2]), _year(numeric[3])
        if a > 12 >= b:
            return _make(year, b, a), False
        if b > 12 >= a:
            return _make(year, a, b), False
        ambiguous = a != b
        day, month = (a, b) if day_first else (b, a)
        return _make(year, month, day), ambiguous
    words = re.fullmatch(rf"(\d{{1,2}})(?:st|nd|rd|th)?[ -]({_MONTH_WORD})[ -](\d{{2}}|\d{{4}})", s)
    if words and words[2].lower() in MONTHS:
        return _make(_year(words[3]), MONTHS[words[2].lower()], int(words[1])), False
    words = re.fullmatch(rf"({_MONTH_WORD})[ -](\d{{1,2}})(?:st|nd|rd|th)?[ -](\d{{4}})", s)
    if words and words[1].lower() in MONTHS:
        return _make(int(words[3]), MONTHS[words[1].lower()], int(words[2])), False
    return None, False


def _year(text: str) -> int:
    year = int(text)
    return year + 2000 if year < 100 else year


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    out = " ".join(text.split())
    return out or None


def norm_invoice_number(text: str | None) -> str | None:
    """Key for duplicate checks: upper case, letters and digits only."""
    if not text:
        return None
    return re.sub(r"[^A-Z0-9]", "", ascii_digits(text).upper()) or None


SUPPLIER_SUFFIXES = re.compile(
    r"\b(LTD|LIMITED|LLC|INC|CO|COMPANY|CORP|CORPORATION|PLC|PVT|PRIVATE|GMBH|SA|BV)\b"
)


def norm_supplier(text: str | None) -> str | None:
    """Key for supplier matching: lower case, no punctuation, no company suffix."""
    if not text:
        return None
    s = re.sub(r"[^A-Z0-9 ]", " ", text.upper())
    s = SUPPLIER_SUFFIXES.sub(" ", s)
    s = " ".join(s.split()).lower()
    return s or None
