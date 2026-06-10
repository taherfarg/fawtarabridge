"""Builders for engine unit tests: a minimal valid invoice, customizable per test."""

from typing import Any

from app.pintae.canonical import CanonicalInvoice, InvoiceLine, Party, VatCategory


def make_line(**overrides: Any) -> InvoiceLine:
    data: dict[str, Any] = {
        "line_id": "1",
        "description": "Test item",
        "quantity": "1",
        "unit_price": "100",
        "vat_category": VatCategory.STANDARD,
        "vat_rate": "5",
    }
    data.update(overrides)
    return InvoiceLine.model_validate(data)


def make_invoice(**overrides: Any) -> CanonicalInvoice:
    data: dict[str, Any] = {
        "invoice_number": "INV-1",
        "issue_date": "2026-05-15",
        "currency": "AED",
        "supplier": Party(name="Supplier LLC", trn="100123456700001"),
        "buyer": Party(name="Buyer LLC", trn="100765432100002"),
        "lines": [make_line()],
    }
    data.update(overrides)
    return CanonicalInvoice.model_validate(data)
