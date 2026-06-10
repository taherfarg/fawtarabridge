from app.core.errors import ErrorDetail
from app.pintae.base import InvoiceEngine
from app.pintae.canonical import CanonicalInvoice
from app.pintae.v1 import rules, serializer


class PintAeV1Engine(InvoiceEngine):
    # SPEC-CHECK: internal version label; map to the official MoF spec version
    # identifier once the final PINT-AE release is published.
    spec_version = "pint-ae-1.0"

    def validate(self, invoice: CanonicalInvoice) -> list[ErrorDetail]:
        return rules.validate(invoice)

    def serialize(self, invoice: CanonicalInvoice) -> bytes:
        return serializer.serialize(invoice)
