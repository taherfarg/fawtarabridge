from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from app.core.errors import ErrorDetail
from app.pintae.canonical import CanonicalInvoice, VatCategory


@dataclass(frozen=True)
class GeneratedXml:
    xml: bytes
    spec_version: str


@dataclass(frozen=True)
class CategoryTotal:
    category: VatCategory
    rate: Decimal
    taxable: Decimal
    tax: Decimal
    exemption_reason: str | None


@dataclass(frozen=True)
class InvoiceTotals:
    line_extension: Decimal
    tax_exclusive: Decimal
    tax_total: Decimal
    tax_inclusive: Decimal
    payable: Decimal
    by_category: list[CategoryTotal]


class InvoiceValidationError(Exception):
    """Raised when XML generation is attempted on an invoice that fails the rules."""

    def __init__(self, errors: list[ErrorDetail]) -> None:
        super().__init__(f"{len(errors)} validation error(s)")
        self.errors = errors


class InvoiceEngine(ABC):
    """One engine per spec version. Implementations must be stateless."""

    spec_version: ClassVar[str]

    @abstractmethod
    def validate(self, invoice: CanonicalInvoice) -> list[ErrorDetail]:
        """Run all business rules; empty list means the invoice is transmittable."""

    @abstractmethod
    def serialize(self, invoice: CanonicalInvoice) -> bytes:
        """Serialize to spec-compliant XML. Assumes :meth:`validate` returned clean."""

    @abstractmethod
    def totals(self, invoice: CanonicalInvoice) -> InvoiceTotals:
        """Computed monetary totals under this spec version's rounding policy."""

    def generate(self, invoice: CanonicalInvoice) -> GeneratedXml:
        """Validate-then-serialize. The only path production code should use —
        the engine never emits XML for an invoice that fails its own rules."""
        errors = self.validate(invoice)
        if errors:
            raise InvoiceValidationError(errors)
        return GeneratedXml(xml=self.serialize(invoice), spec_version=self.spec_version)
