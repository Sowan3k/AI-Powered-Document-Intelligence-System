"""Random invoice data with exact Decimal arithmetic."""

import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
SUPPLIERS = [
    "Acme Traders Ltd", "Bengal Office Supplies", "Northwind Logistics", "Padma Printing House",
    "Delta Hardware Co", "Sundarban Foods Ltd", "Meghna Tech Services", "Blue River Stationers",
]  # fmt: skip
CUSTOMERS = [
    "Kawsar Garments Ltd", "Riverside Clinic", "Green Valley School", "Orion Builders",
    "Lakeview Hotel", "Crescent Pharma",
]  # fmt: skip
ITEMS = [
    ("A4 paper ream", "4.50"), ("Toner cartridge", "62.00"), ("Delivery charge", "15.00"),
    ("Office chair", "120.00"), ("USB keyboard", "18.75"), ("Printing, per page", "0.125"),
    ("Consulting hour", "45.00"), ("Steel bolts, box", "7.20"), ("Rice, 25 kg bag", "21.40"),
    ("Network cable, 10 m", "6.35"),
]  # fmt: skip
CURRENCIES = ["USD", "EUR", "BDT", "GBP"]
TAX_RATES = [Decimal("0"), Decimal("5"), Decimal("7.5"), Decimal("10"), Decimal("15")]


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


@dataclass
class Adjustment:
    label: str
    amount: Decimal  # signed: a discount is negative


@dataclass
class Invoice:
    invoice_number: str
    invoice_date: date
    supplier_name: str
    customer_name: str | None
    currency: str
    line_items: list[LineItem]
    subtotal: Decimal
    tax: Decimal | None
    total: Decimal
    tax_rate: Decimal = Decimal("0")
    planted: list[str] = field(default_factory=list)  # errors put in on purpose
    # Discounts and charges between subtotal and total (D57).
    adjustments: list[Adjustment] = field(default_factory=list)

    def truth(self) -> dict:
        """Ground truth as JSON-ready values (Decimals as strings, dates as ISO)."""

        def plain(value: object) -> object:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, list):
                return [plain(v) for v in value]
            if isinstance(value, dict):
                return {k: plain(v) for k, v in value.items()}
            return value

        data = plain(asdict(self))
        data.pop("tax_rate")
        return data  # type: ignore[return-value]


def make_invoice(rng: random.Random, number: int, currency: str | None = None) -> Invoice:
    items = []
    for description, price in rng.sample(ITEMS, rng.randint(2, 5)):
        quantity = Decimal(rng.choice(["1", "2", "3", "5", "10", "12", "40", "2.5"]))
        unit_price = Decimal(price)
        items.append(LineItem(description, quantity, unit_price, money(quantity * unit_price)))
    subtotal = sum((item.amount for item in items), Decimal("0"))
    rate = rng.choice(TAX_RATES)
    tax = money(subtotal * rate / 100)
    return Invoice(
        invoice_number=f"INV-{2026}-{number:05d}",
        invoice_date=date(2026, 1, 5) + timedelta(days=rng.randint(0, 290)),
        supplier_name=rng.choice(SUPPLIERS),
        customer_name=rng.choice(CUSTOMERS),
        currency=currency or rng.choice(CURRENCIES),
        line_items=items,
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
        tax_rate=rate,
    )


BD_SUPPLIERS = ["Karnaphuli Traders Ltd", "Jamuna Textile Mills", "Rupsha Agro Industries"]
BD_CUSTOMERS = ["Kawsar Garments Ltd", "Meghna Pharma Ltd", "Shapla Builders"]
BD_ITEMS = [
    ("Cotton fabric, roll", "12500.00"), ("Industrial sewing machine", "85000.00"),
    ("Printing ink, 5 litre", "3450.00"), ("Carton box, 100 pcs", "2200.00"),
    ("Steel rack", "18750.00"),
]  # fmt: skip
RECEIPT_ITEMS = [
    ("Chicken biryani", "350.00"), ("Beef tehari", "280.00"), ("Borhani", "90.00"),
    ("Firni", "120.00"), ("Mineral water", "30.00"),
]  # fmt: skip


def _items(rng: random.Random, menu: list[tuple[str, str]], quantities: list[str]) -> list:
    items = []
    for description, price in rng.sample(menu, rng.randint(2, 4)):
        quantity, unit_price = Decimal(rng.choice(quantities)), Decimal(price)
        items.append(LineItem(description, quantity, unit_price, money(quantity * unit_price)))
    return items


def make_bd_invoice(rng: random.Random, number: int) -> Invoice:
    """A Bangladeshi VAT invoice: Tk amounts in lakh grouping, VAT 15% after a
    discount, and a delivery charge."""
    items = _items(rng, BD_ITEMS, ["2", "4", "5", "10"])
    subtotal = sum((i.amount for i in items), Decimal("0"))
    discount = money(subtotal * Decimal("0.05"))
    tax = money((subtotal - discount) * Decimal("0.15"))
    delivery = Decimal("1500.00")
    return Invoice(
        invoice_number=f"KTL/2026/{number:04d}",
        invoice_date=date(2026, 1, 5) + timedelta(days=rng.randint(0, 290)),
        supplier_name=rng.choice(BD_SUPPLIERS),
        customer_name=rng.choice(BD_CUSTOMERS),
        currency="BDT",
        line_items=items,
        subtotal=subtotal,
        tax=tax,
        total=subtotal - discount + tax + delivery,
        tax_rate=Decimal("15"),
        adjustments=[Adjustment("Discount", -discount), Adjustment("Delivery charge", delivery)],
    )


def make_receipt(rng: random.Random, number: int) -> Invoice:
    """A restaurant bill: VAT 5% and a 10% service charge, no customer name."""
    items = _items(rng, RECEIPT_ITEMS, ["1", "2", "3"])
    subtotal = sum((i.amount for i in items), Decimal("0"))
    service = money(subtotal * Decimal("0.10"))
    tax = money(subtotal * Decimal("0.05"))
    return Invoice(
        invoice_number=f"R-{number:05d}",
        invoice_date=date(2026, 1, 5) + timedelta(days=rng.randint(0, 290)),
        supplier_name="Dhaka Kitchen",
        customer_name=None,
        currency="BDT",
        line_items=items,
        subtotal=subtotal,
        tax=tax,
        total=subtotal + service + tax,
        tax_rate=Decimal("5"),
        # A bill names no customer, so R01 warns about it: label it, not hide it.
        planted=["missing_customer"],
        adjustments=[Adjustment("Service charge 10%", service)],
    )


def plant(invoice: Invoice, error: str) -> Invoice:
    """Put a known error into an invoice, for the validation tests."""
    if error == "wrong_total":
        invoice.total += Decimal("10.00")
    elif error == "wrong_line_sum":
        invoice.subtotal += Decimal("5.00")
        invoice.total += Decimal("5.00")
    elif error == "missing_tax":
        invoice.tax = None
        invoice.total = invoice.subtotal
    elif error == "missing_customer":
        invoice.customer_name = None
    elif error == "wrong_line_amount":
        # One line's amount is off; subtotal and total follow it, so only R04 fires.
        invoice.line_items[0].amount += Decimal("1.00")
        invoice.subtotal += Decimal("1.00")
        invoice.total += Decimal("1.00")
    elif error == "future_date":
        invoice.invoice_date = date(2099, 1, 15)
    else:
        raise ValueError(error)
    invoice.planted.append(error)
    return invoice
