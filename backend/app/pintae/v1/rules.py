"""Business rules for spec v1 — Schematron-style, as pure Python functions.

Each rule takes the invoice and returns a list of bilingual ErrorDetail (empty =
pass). ``validate`` runs them all and concatenates, so a customer sees every
problem at once, not one per round-trip. Rule order is deterministic (header →
parties → lines → arithmetic) for stable golden files.
"""

from collections.abc import Callable

from app.core.errors import ErrorDetail, build_error_detail
from app.pintae.canonical import CanonicalInvoice, VatCategory
from app.pintae.v1.calc import (
    CATEGORY_RATES,
    compute_totals,
    decimal_places,
    line_net,
    line_vat,
)
from app.schemas.common import TRN_RE

Rule = Callable[[CanonicalInvoice], list[ErrorDetail]]


def _err(error_code: str, field: str | None = None, **params: str) -> ErrorDetail:
    return build_error_detail(error_code, field=field, params=params)


# --------------------------------------------------------------------- header


def rule_invoice_number(inv: CanonicalInvoice) -> list[ErrorDetail]:
    if not inv.invoice_number:
        return [_err("invoice.number_missing", field="invoice_number")]
    return []


def rule_type_code(inv: CanonicalInvoice) -> list[ErrorDetail]:
    # SPEC-CHECK: only 380 (commercial invoice) in v1; 381 credit notes are the
    # Phase-2 corrections workflow.
    if inv.invoice_type_code != "380":
        return [
            _err(
                "invoice.type_code_unsupported",
                field="invoice_type_code",
                code=inv.invoice_type_code,
            )
        ]
    return []


def rule_currency(inv: CanonicalInvoice) -> list[ErrorDetail]:
    # SPEC-CHECK: v1 restricts invoices to AED. Foreign-currency invoices need
    # TaxCurrencyCode + exchange-rate handling — deliberately out of v1 scope.
    if inv.currency != "AED":
        return [_err("invoice.currency_unsupported", field="currency", currency=inv.currency)]
    return []


def rule_dates(inv: CanonicalInvoice) -> list[ErrorDetail]:
    if inv.due_date is not None and inv.due_date < inv.issue_date:
        return [
            _err(
                "invoice.due_date_before_issue",
                field="due_date",
                due_date=inv.due_date.isoformat(),
                issue_date=inv.issue_date.isoformat(),
            )
        ]
    return []


# -------------------------------------------------------------------- parties


def _party_errors(inv: CanonicalInvoice, which: str) -> list[ErrorDetail]:
    party = getattr(inv, which)
    errors: list[ErrorDetail] = []
    if not party.name:
        errors.append(_err(f"invoice.{which}_name_missing", field=f"{which}.name"))
    if not party.trn:
        # SPEC-CHECK: buyer TRN mandatory assumes B2B "standard" invoices (the MVP
        # scope). B2C/simplified invoices would relax this for the buyer.
        errors.append(_err(f"invoice.{which}_trn_missing", field=f"{which}.trn"))
    elif not TRN_RE.fullmatch(party.trn):
        errors.append(_err(f"invoice.{which}_trn_invalid", field=f"{which}.trn", value=party.trn))
    return errors


def rule_supplier(inv: CanonicalInvoice) -> list[ErrorDetail]:
    return _party_errors(inv, "supplier")


def rule_buyer(inv: CanonicalInvoice) -> list[ErrorDetail]:
    return _party_errors(inv, "buyer")


# ---------------------------------------------------------------------- lines


def rule_lines_present(inv: CanonicalInvoice) -> list[ErrorDetail]:
    if not inv.lines:
        return [_err("invoice.lines_empty", field="lines")]
    return []


def rule_line_ids(inv: CanonicalInvoice) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    seen: set[str] = set()
    for i, line in enumerate(inv.lines):
        field = f"lines[{i}].line_id"
        if not line.line_id:
            errors.append(_err("invoice.line.id_missing", field=field))
        elif line.line_id in seen:
            errors.append(_err("invoice.line.duplicate_id", field=field, line_id=line.line_id))
        else:
            seen.add(line.line_id)
    return errors


def rule_line_content(inv: CanonicalInvoice) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    for i, line in enumerate(inv.lines):
        prefix = f"lines[{i}]"
        if not line.description:
            errors.append(_err("invoice.line.description_missing", field=f"{prefix}.description"))
        if line.quantity <= 0:
            errors.append(
                _err(
                    "invoice.line.quantity_invalid",
                    field=f"{prefix}.quantity",
                    actual=str(line.quantity),
                )
            )
        if line.unit_price < 0:
            errors.append(
                _err(
                    "invoice.line.price_invalid",
                    field=f"{prefix}.unit_price",
                    actual=str(line.unit_price),
                )
            )
        gross = line.quantity * line.unit_price
        # Discounts are monetary amounts: sub-fils precision would be silently lost
        # in the 2-decimal XML, so it is rejected instead of rounded.
        sub_fils = decimal_places(line.discount_amount) > 2
        if line.discount_amount < 0 or sub_fils or (gross >= 0 and line.discount_amount > gross):
            errors.append(
                _err(
                    "invoice.line.discount_invalid",
                    field=f"{prefix}.discount_amount",
                    actual=str(line.discount_amount),
                )
            )
    return errors


def rule_vat_rates(inv: CanonicalInvoice) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    for i, line in enumerate(inv.lines):
        expected = CATEGORY_RATES[line.vat_category]
        if line.vat_rate != expected:
            errors.append(
                _err(
                    "invoice.line.vat_rate_mismatch",
                    field=f"lines[{i}].vat_rate",
                    category=line.vat_category.value,
                    expected=str(expected),
                    actual=str(line.vat_rate),
                )
            )
    return errors


def rule_exemption_reasons(inv: CanonicalInvoice) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    reason_categories = (
        VatCategory.EXEMPT,
        VatCategory.REVERSE_CHARGE,
        VatCategory.OUT_OF_SCOPE,
    )
    for i, line in enumerate(inv.lines):
        needs_reason = line.vat_category in reason_categories
        if needs_reason and not line.exemption_reason:
            errors.append(
                _err(
                    "invoice.line.exemption_reason_missing",
                    field=f"lines[{i}].exemption_reason",
                    category=line.vat_category.value,
                )
            )
    return errors


# ----------------------------------------------------------------- arithmetic


def rule_declared_line_amounts(inv: CanonicalInvoice) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    for i, line in enumerate(inv.lines):
        if line.declared_net_amount is not None:
            expected = line_net(line)
            if line.declared_net_amount != expected:
                errors.append(
                    _err(
                        "invoice.calc.line_net_mismatch",
                        field=f"lines[{i}].declared_net_amount",
                        expected=str(expected),
                        actual=str(line.declared_net_amount),
                    )
                )
        if line.declared_vat_amount is not None:
            expected = line_vat(line)
            if line.declared_vat_amount != expected:
                errors.append(
                    _err(
                        "invoice.calc.line_vat_mismatch",
                        field=f"lines[{i}].declared_vat_amount",
                        expected=str(expected),
                        actual=str(line.declared_vat_amount),
                    )
                )
    return errors


def rule_declared_totals(inv: CanonicalInvoice) -> list[ErrorDetail]:
    if not inv.lines:
        return []  # nothing to compare against; lines_empty already reported
    totals = compute_totals(inv)
    checks = [
        (
            "declared_total_excluding_vat",
            inv.declared_total_excluding_vat,
            totals.tax_exclusive,
            "invoice.calc.total_excl_mismatch",
        ),
        (
            "declared_total_vat",
            inv.declared_total_vat,
            totals.tax_total,
            "invoice.calc.total_vat_mismatch",
        ),
        (
            "declared_total_including_vat",
            inv.declared_total_including_vat,
            totals.tax_inclusive,
            "invoice.calc.total_incl_mismatch",
        ),
    ]
    errors: list[ErrorDetail] = []
    for field, declared, expected, code in checks:
        if declared is not None and declared != expected:
            errors.append(_err(code, field=field, expected=str(expected), actual=str(declared)))
    return errors


RULES: list[Rule] = [
    rule_invoice_number,
    rule_type_code,
    rule_currency,
    rule_dates,
    rule_supplier,
    rule_buyer,
    rule_lines_present,
    rule_line_ids,
    rule_line_content,
    rule_vat_rates,
    rule_exemption_reasons,
    rule_declared_line_amounts,
    rule_declared_totals,
]


def validate(invoice: CanonicalInvoice) -> list[ErrorDetail]:
    errors: list[ErrorDetail] = []
    for rule in RULES:
        errors.extend(rule(invoice))
    return errors


# Every code the v1 rules can emit. The i18n catalog-completeness test asserts a
# bilingual entry exists for each (some codes are built dynamically, so a static
# source scan cannot find them).
ERROR_CODES: frozenset[str] = frozenset(
    {
        "invoice.number_missing",
        "invoice.type_code_unsupported",
        "invoice.currency_unsupported",
        "invoice.due_date_before_issue",
        "invoice.supplier_name_missing",
        "invoice.supplier_trn_missing",
        "invoice.supplier_trn_invalid",
        "invoice.buyer_name_missing",
        "invoice.buyer_trn_missing",
        "invoice.buyer_trn_invalid",
        "invoice.lines_empty",
        "invoice.line.id_missing",
        "invoice.line.duplicate_id",
        "invoice.line.description_missing",
        "invoice.line.quantity_invalid",
        "invoice.line.price_invalid",
        "invoice.line.discount_invalid",
        "invoice.line.vat_rate_mismatch",
        "invoice.line.exemption_reason_missing",
        "invoice.calc.line_net_mismatch",
        "invoice.calc.line_vat_mismatch",
        "invoice.calc.total_excl_mismatch",
        "invoice.calc.total_vat_mismatch",
        "invoice.calc.total_incl_mismatch",
    }
)

__all__ = ["ERROR_CODES", "RULES", "Rule", "validate"]
