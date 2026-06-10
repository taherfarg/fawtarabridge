"""Canonical invoice model — the single source of truth (architecture rule 1).

Design notes:
- The model is deliberately *structurally* permissive (empty strings, zero
  quantities): business validation lives in the versioned rule layer so every
  violation becomes a precise bilingual error instead of a raw pydantic exception.
- VAT category and rate are structurally REQUIRED: defaulting them would amount to
  guessing tax treatment, which this product never does (DECISIONS D-017).
- ``declared_*`` fields carry totals the customer supplied (e.g. CSV columns).
  They are cross-checked against computed values and NEVER silently replaced.
- All monetary values are ``Decimal``; pydantic serializes them as JSON strings,
  so nothing ever round-trips through binary floats.
"""

import enum
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class VatCategory(enum.StrEnum):
    """UAE VAT treatment per line, using UNCL5305-style codes as in Peppol PINT.

    # SPEC-CHECK: PINT-AE may define additional categories (e.g. 'O' out of scope,
    # margin schemes). v1 supports the four required by the MVP instructions.
    """

    STANDARD = "S"  # 5%
    ZERO_RATED = "Z"  # 0%
    EXEMPT = "E"  # 0%, exemption reason required
    REVERSE_CHARGE = "AE"  # 0%, buyer accounts for VAT


class Address(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    street: str | None = None
    city: str | None = None
    emirate: str | None = None
    country_code: str = "AE"


class Party(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = ""
    name_ar: str | None = None
    trn: str | None = None
    # Electronic address as "scheme:identifier" (e.g. "0235:100123456700001").
    # SPEC-CHECK: the UAE Peppol participant scheme ID must be confirmed with the ASP.
    peppol_id: str | None = None
    address: Address = Field(default_factory=Address)


class InvoiceLine(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    line_id: str = ""
    description: str = ""
    description_ar: str | None = None
    quantity: Decimal = Decimal("0")
    unit_code: str = "C62"  # UN/ECE Recommendation 20: "one" (each)
    unit_price: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    vat_category: VatCategory
    vat_rate: Decimal
    exemption_reason: str | None = None
    # Customer-declared values (e.g. from a CSV column) — cross-checked, never coerced.
    declared_net_amount: Decimal | None = None
    declared_vat_amount: Decimal | None = None


class CanonicalInvoice(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    invoice_number: str = ""
    issue_date: date
    due_date: date | None = None
    # UNCL1001: 380 = commercial invoice. 381 (credit note) arrives with the
    # corrections workflow (PRD Phase 2).
    invoice_type_code: str = "380"
    currency: str = "AED"
    note: str | None = None
    supplier: Party = Field(default_factory=Party)
    buyer: Party = Field(default_factory=Party)
    lines: list[InvoiceLine] = Field(default_factory=list)
    # Customer-declared header totals — cross-checked, never coerced.
    declared_total_excluding_vat: Decimal | None = None
    declared_total_vat: Decimal | None = None
    declared_total_including_vat: Decimal | None = None
