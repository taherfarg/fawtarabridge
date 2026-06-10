from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from app.core.errors import ErrorDetail
from app.pintae.canonical import CanonicalInvoice


@dataclass(frozen=True)
class GeneratedXml:
    xml: bytes
    spec_version: str


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

    def generate(self, invoice: CanonicalInvoice) -> GeneratedXml:
        """Validate-then-serialize. The only path production code should use —
        the engine never emits XML for an invoice that fails its own rules."""
        errors = self.validate(invoice)
        if errors:
            raise InvoiceValidationError(errors)
        return GeneratedXml(xml=self.serialize(invoice), spec_version=self.spec_version)
