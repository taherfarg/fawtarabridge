import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import ErrorDetail
from app.pintae.canonical import CanonicalInvoice, VatCategory


class BuyerIn(BaseModel):
    """Inline buyer. TRN/format problems surface as engine validation errors (the
    invoice-level bilingual report), not as request-shape 422s."""

    name: str = Field(min_length=1, max_length=255)
    name_ar: str | None = None
    trn: str | None = None
    peppol_id: str | None = None
    street: str | None = None
    city: str | None = None
    emirate: str | None = None
    country_code: str = "AE"


class InvoiceLineIn(BaseModel):
    line_id: str | None = None  # auto-numbered "1".."n" when omitted
    description: str = ""
    description_ar: str | None = None
    quantity: Decimal = Decimal("0")
    unit_code: str = "C62"
    unit_price: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    vat_category: VatCategory
    vat_rate: Decimal
    exemption_reason: str | None = None
    declared_net_amount: Decimal | None = None
    declared_vat_amount: Decimal | None = None


class InvoiceCreateIn(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=100)
    issue_date: date
    due_date: date | None = None
    note: str | None = None
    buyer_contact_id: uuid.UUID | None = None
    buyer: BuyerIn | None = None
    lines: list[InvoiceLineIn] = Field(min_length=1)
    declared_total_excluding_vat: Decimal | None = None
    declared_total_vat: Decimal | None = None
    declared_total_including_vat: Decimal | None = None

    @model_validator(mode="after")
    def buyer_or_contact(self) -> "InvoiceCreateIn":
        if self.buyer is None and self.buyer_contact_id is None:
            raise ValueError("either buyer or buyer_contact_id is required")
        return self


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    status: str
    issue_date: date
    buyer_name: str
    buyer_trn: str | None
    total_including_vat: Decimal
    duplicate_warning: bool
    spec_version: str | None
    buyer_contact_id: uuid.UUID | None


class InvoiceDetailOut(InvoiceOut):
    canonical: CanonicalInvoice
    errors: list[ErrorDetail]
    warnings: list[ErrorDetail]


class InvoiceCreateOut(BaseModel):
    invoice: InvoiceOut
    errors: list[ErrorDetail]
    warnings: list[ErrorDetail]


class InvoiceListOut(BaseModel):
    items: list[InvoiceOut]
    total: int
    limit: int
    offset: int


class ValidationReportOut(BaseModel):
    status: str
    spec_version: str | None
    errors: list[ErrorDetail]
    warnings: list[ErrorDetail]
