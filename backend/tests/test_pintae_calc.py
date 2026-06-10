from decimal import Decimal

from app.pintae.canonical import CanonicalInvoice, InvoiceLine, VatCategory
from app.pintae.v1.calc import compute_totals, line_net, line_vat, round2
from tests.pintae_builders import make_invoice, make_line


def test_round2_half_up() -> None:
    assert round2(Decimal("0.005")) == Decimal("0.01")
    assert round2(Decimal("0.004")) == Decimal("0.00")
    assert round2(Decimal("1.115")) == Decimal("1.12")
    assert round2(Decimal("2.675")) == Decimal("2.68")  # would be 2.67 with bankers' rounding
    assert round2(Decimal("100.005")) == Decimal("100.01")


def test_line_net_applies_discount_then_rounds_once() -> None:
    line = make_line(quantity="3", unit_price="150.50", discount_amount="51.50")
    assert line_net(line) == Decimal("400.00")


def test_line_net_rounding_edge() -> None:
    assert line_net(make_line(quantity="1", unit_price="0.105")) == Decimal("0.11")
    assert line_net(make_line(quantity="3", unit_price="33.335")) == Decimal("100.01")


def test_line_vat_standard_rate() -> None:
    line = make_line(quantity="10", unit_price="100")
    assert line_vat(line) == Decimal("50.00")


def test_vat_is_computed_per_category_not_per_line() -> None:
    # Two lines of net 0.11: per-line VAT would be 0.01 + 0.01 = 0.02,
    # per-category VAT is round2(0.22 * 5%) = 0.01. We lock the per-category rule.
    invoice = make_invoice(
        lines=[
            make_line(line_id="1", quantity="1", unit_price="0.105"),
            make_line(line_id="2", quantity="1", unit_price="0.105"),
        ]
    )
    totals = compute_totals(invoice)
    assert totals.line_extension == Decimal("0.22")
    assert totals.tax_total == Decimal("0.01")
    assert sum(line_vat(ln) for ln in invoice.lines) == Decimal("0.02")  # the difference


def test_compute_totals_groups_and_sorts_categories() -> None:
    invoice = make_invoice(
        lines=[
            make_line(line_id="1", quantity="1", unit_price="100"),  # S 5%
            make_line(
                line_id="2",
                quantity="1",
                unit_price="200",
                vat_category=VatCategory.ZERO_RATED,
                vat_rate="0",
            ),
            make_line(
                line_id="3",
                quantity="1",
                unit_price="300",
                vat_category=VatCategory.EXEMPT,
                vat_rate="0",
                exemption_reason="Exempt — Article 42",
            ),
        ]
    )
    totals = compute_totals(invoice)
    assert [ct.category for ct in totals.by_category] == [
        VatCategory.EXEMPT,
        VatCategory.STANDARD,
        VatCategory.ZERO_RATED,
    ]
    exempt = totals.by_category[0]
    assert exempt.taxable == Decimal("300.00")
    assert exempt.tax == Decimal("0.00")
    assert exempt.exemption_reason == "Exempt — Article 42"

    assert totals.line_extension == Decimal("600.00")
    assert totals.tax_total == Decimal("5.00")
    assert totals.tax_inclusive == Decimal("605.00")
    assert totals.payable == Decimal("605.00")


def test_compute_totals_empty_invoice_is_all_zero() -> None:
    invoice = CanonicalInvoice(issue_date="2026-05-15")  # type: ignore[arg-type]
    totals = compute_totals(invoice)
    assert totals.line_extension == Decimal("0.00")
    assert totals.tax_total == Decimal("0.00")
    assert totals.by_category == []


def test_quantity_times_price_uses_full_precision_before_rounding() -> None:
    # 7 * 14.285 = 99.995 -> 100.00 only if rounding happens after multiplication.
    line: InvoiceLine = make_line(quantity="7", unit_price="14.285")
    assert line_net(line) == Decimal("100.00")
