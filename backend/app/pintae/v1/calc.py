"""Monetary arithmetic for spec v1. Pure functions, Decimal-only.

Rounding policy (v1):
- All monetary amounts are rounded to 2 decimals (AED fils) with ROUND_HALF_UP.
  # SPEC-CHECK: confirm the official rounding mode; FTA practice is round-to-fils,
  # half-up assumed here.
- Line net = quantity * unit_price - discount, rounded once at the line level.
- VAT is computed PER CATEGORY from the category taxable sum (EN 16931 / Peppol
  convention), not by summing per-line VAT — the two can differ by fils.
  # SPEC-CHECK: confirm PINT-AE follows the EN 16931 per-category computation.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.pintae.base import CategoryTotal, InvoiceTotals
from app.pintae.canonical import CanonicalInvoice, InvoiceLine, VatCategory

TWO_PLACES = Decimal("0.01")

# Fixed rates per category — 5% standard confirmed by PINT AE Billing v1.0.3.
CATEGORY_RATES: dict[VatCategory, Decimal] = {
    VatCategory.STANDARD: Decimal("5"),
    VatCategory.ZERO_RATED: Decimal("0"),
    VatCategory.EXEMPT: Decimal("0"),
    VatCategory.REVERSE_CHARGE: Decimal("0"),
    VatCategory.OUT_OF_SCOPE: Decimal("0"),
}


def round2(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def line_gross(line: InvoiceLine) -> Decimal:
    return line.quantity * line.unit_price


def line_net(line: InvoiceLine) -> Decimal:
    return round2(line_gross(line) - line.discount_amount)


def line_vat(line: InvoiceLine) -> Decimal:
    """Per-line VAT, informational (declared-value cross-checks). The
    authoritative tax total is per-category — see :func:`compute_totals`."""
    return round2(line_net(line) * line.vat_rate / Decimal("100"))


def compute_totals(invoice: CanonicalInvoice) -> InvoiceTotals:
    nets = [line_net(line) for line in invoice.lines]
    line_extension = round2(sum(nets, Decimal("0")))

    groups: dict[tuple[VatCategory, Decimal], list[InvoiceLine]] = {}
    for line in invoice.lines:
        groups.setdefault((line.vat_category, line.vat_rate), []).append(line)

    by_category: list[CategoryTotal] = []
    for (category, rate), lines in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        taxable = round2(sum((line_net(ln) for ln in lines), Decimal("0")))
        tax = round2(taxable * rate / Decimal("100"))
        reason = next((ln.exemption_reason for ln in lines if ln.exemption_reason), None)
        by_category.append(
            CategoryTotal(
                category=category, rate=rate, taxable=taxable, tax=tax, exemption_reason=reason
            )
        )

    tax_total = round2(sum((ct.tax for ct in by_category), Decimal("0")))
    tax_exclusive = line_extension  # no document-level allowances/charges in v1
    tax_inclusive = round2(tax_exclusive + tax_total)
    return InvoiceTotals(
        line_extension=line_extension,
        tax_exclusive=tax_exclusive,
        tax_total=tax_total,
        tax_inclusive=tax_inclusive,
        payable=tax_inclusive,  # no prepayments in v1
        by_category=by_category,
    )
