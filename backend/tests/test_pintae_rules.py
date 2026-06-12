"""Unit tests for every v1 business rule (Schematron-style pure functions)."""

from decimal import Decimal

from app.pintae.canonical import Party, VatCategory
from app.pintae.v1 import rules
from tests.pintae_builders import make_invoice, make_line


def codes(errors: list) -> list[str]:
    return [e.code for e in errors]


def test_clean_invoice_has_no_errors() -> None:
    assert rules.validate(make_invoice()) == []


def test_every_error_is_bilingual() -> None:
    invoice = make_invoice(
        invoice_number="",
        currency="USD",
        supplier=Party(),
        buyer=Party(),
        lines=[],
    )
    errors = rules.validate(invoice)
    assert errors
    for error in errors:
        assert error.message_en, error.code
        assert error.message_ar, error.code
        assert error.code in rules.ERROR_CODES


# ------------------------------------------------------------------ header rules


def test_rule_invoice_number() -> None:
    assert rules.rule_invoice_number(make_invoice(invoice_number="")) != []
    assert rules.rule_invoice_number(make_invoice()) == []


def test_rule_type_code_only_380() -> None:
    errors = rules.rule_type_code(make_invoice(invoice_type_code="381"))
    assert codes(errors) == ["invoice.type_code_unsupported"]
    assert "381" in errors[0].message_en
    assert rules.rule_type_code(make_invoice()) == []


def test_rule_currency_aed_only() -> None:
    errors = rules.rule_currency(make_invoice(currency="USD"))
    assert codes(errors) == ["invoice.currency_unsupported"]
    assert "USD" in errors[0].message_ar
    assert rules.rule_currency(make_invoice()) == []


def test_rule_dates() -> None:
    bad = make_invoice(issue_date="2026-05-15", due_date="2026-05-01")
    errors = rules.rule_dates(bad)
    assert codes(errors) == ["invoice.due_date_before_issue"]
    assert rules.rule_dates(make_invoice(due_date="2026-06-14")) == []
    assert rules.rule_dates(make_invoice()) == []  # no due date at all


# ----------------------------------------------------------------- party rules


def test_supplier_trn_missing_and_invalid() -> None:
    no_trn = make_invoice(supplier=Party(name="S"))
    assert codes(rules.rule_supplier(no_trn)) == ["invoice.supplier_trn_missing"]

    bad_trn = make_invoice(supplier=Party(name="S", trn="123"))
    errors = rules.rule_supplier(bad_trn)
    assert codes(errors) == ["invoice.supplier_trn_invalid"]
    assert errors[0].field == "supplier.trn"
    assert "123" in errors[0].message_en


def test_buyer_name_and_trn() -> None:
    invoice = make_invoice(buyer=Party())
    assert codes(rules.rule_buyer(invoice)) == [
        "invoice.buyer_name_missing",
        "invoice.buyer_trn_missing",
    ]


def test_trn_with_letters_rejected() -> None:
    invoice = make_invoice(buyer=Party(name="B", trn="10012345670000A"))
    assert codes(rules.rule_buyer(invoice)) == ["invoice.buyer_trn_invalid"]


# ------------------------------------------------------------------ line rules


def test_rule_lines_present() -> None:
    assert codes(rules.rule_lines_present(make_invoice(lines=[]))) == ["invoice.lines_empty"]


def test_rule_line_ids_missing_and_duplicate() -> None:
    invoice = make_invoice(
        lines=[
            make_line(line_id=""),
            make_line(line_id="7"),
            make_line(line_id="7"),
        ]
    )
    errors = rules.rule_line_ids(invoice)
    assert codes(errors) == ["invoice.line.id_missing", "invoice.line.duplicate_id"]
    assert errors[0].field == "lines[0].line_id"
    assert errors[1].field == "lines[2].line_id"


def test_rule_line_content_quantity_price_discount() -> None:
    invoice = make_invoice(
        lines=[
            make_line(quantity="0"),
            make_line(unit_price="-5"),
            make_line(unit_price="100", discount_amount="500"),
            make_line(description=""),
        ]
    )
    errors = rules.rule_line_content(invoice)
    assert codes(errors) == [
        "invoice.line.quantity_invalid",
        "invoice.line.price_invalid",
        "invoice.line.discount_invalid",
        "invoice.line.description_missing",
    ]


def test_discount_with_sub_fils_precision_rejected() -> None:
    # A 3-decimal discount would be silently rounded in the 2-decimal XML — reject it.
    invoice = make_invoice(lines=[make_line(unit_price="100", discount_amount="10.005")])
    assert codes(rules.rule_line_content(invoice)) == ["invoice.line.discount_invalid"]
    ok = make_invoice(lines=[make_line(unit_price="100", discount_amount="10.05")])
    assert rules.rule_line_content(ok) == []


def test_rule_vat_rate_must_match_category() -> None:
    cases = [
        (VatCategory.STANDARD, "5", True),
        (VatCategory.STANDARD, "0", False),
        (VatCategory.STANDARD, "12", False),
        (VatCategory.ZERO_RATED, "0", True),
        (VatCategory.ZERO_RATED, "5", False),
        (VatCategory.EXEMPT, "0", True),
        (VatCategory.REVERSE_CHARGE, "0", True),
        (VatCategory.REVERSE_CHARGE, "5", False),
        (VatCategory.OUT_OF_SCOPE, "0", True),
        (VatCategory.OUT_OF_SCOPE, "5", False),
    ]
    for category, rate, ok in cases:
        invoice = make_invoice(
            lines=[make_line(vat_category=category, vat_rate=rate, exemption_reason="r")]
        )
        errors = rules.rule_vat_rates(invoice)
        assert (errors == []) is ok, f"{category} @ {rate}%"


def test_rule_exemption_reason_required_for_e_and_ae() -> None:
    for category in (VatCategory.EXEMPT, VatCategory.REVERSE_CHARGE, VatCategory.OUT_OF_SCOPE):
        invoice = make_invoice(lines=[make_line(vat_category=category, vat_rate="0")])
        assert codes(rules.rule_exemption_reasons(invoice)) == [
            "invoice.line.exemption_reason_missing"
        ]
    # S and Z don't need one
    invoice = make_invoice(lines=[make_line(vat_category=VatCategory.ZERO_RATED, vat_rate="0")])
    assert rules.rule_exemption_reasons(invoice) == []


# ------------------------------------------------------------------ arithmetic


def test_declared_line_amounts_cross_checked() -> None:
    invoice = make_invoice(
        lines=[
            make_line(
                quantity="2",
                unit_price="50",
                declared_net_amount="90.00",
                declared_vat_amount="7.00",
            )
        ]
    )
    errors = rules.rule_declared_line_amounts(invoice)
    assert codes(errors) == [
        "invoice.calc.line_net_mismatch",
        "invoice.calc.line_vat_mismatch",
    ]
    assert "100.00" in errors[0].message_en  # expected value is shown to the user
    assert "5.00" in errors[1].message_en


def test_declared_line_amounts_pass_when_exact() -> None:
    invoice = make_invoice(
        lines=[
            make_line(
                quantity="2",
                unit_price="50",
                declared_net_amount="100.00",
                declared_vat_amount="5.00",
            )
        ]
    )
    assert rules.rule_declared_line_amounts(invoice) == []


def test_declared_totals_cross_checked() -> None:
    invoice = make_invoice(
        declared_total_excluding_vat=Decimal("999.00"),
        declared_total_vat=Decimal("55.00"),
        declared_total_including_vat=Decimal("1100.00"),
        lines=[make_line(quantity="10", unit_price="100")],
    )
    errors = rules.rule_declared_totals(invoice)
    assert codes(errors) == [
        "invoice.calc.total_excl_mismatch",
        "invoice.calc.total_vat_mismatch",
        "invoice.calc.total_incl_mismatch",
    ]


def test_declared_totals_skipped_when_lines_empty() -> None:
    invoice = make_invoice(lines=[], declared_total_vat=Decimal("55.00"))
    assert rules.rule_declared_totals(invoice) == []


def test_validate_collects_all_errors_in_rule_order() -> None:
    invoice = make_invoice(
        invoice_number="",
        currency="USD",
        lines=[make_line(quantity="0")],
    )
    got = codes(rules.validate(invoice))
    assert got == [
        "invoice.number_missing",
        "invoice.currency_unsupported",
        "invoice.line.quantity_invalid",
    ]
