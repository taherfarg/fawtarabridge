"""PINT-AE engine package.

Public surface:
- :class:`CanonicalInvoice` — the single source of truth every intake path feeds.
- :func:`get_engine` — returns the engine for a spec version (default from settings).

Versioning: each spec version is a self-contained subpackage (``v1``, later ``v2``)
registered here. Adding a version must never touch existing version code paths.
"""

from app.pintae.base import GeneratedXml, InvoiceEngine, InvoiceValidationError
from app.pintae.canonical import Address, CanonicalInvoice, InvoiceLine, Party, VatCategory
from app.pintae.registry import (
    UnknownSpecVersionError,
    available_spec_versions,
    get_engine,
    register_engine,
)
from app.pintae.v1 import PintAeV1Engine

register_engine(PintAeV1Engine())

__all__ = [
    "Address",
    "CanonicalInvoice",
    "GeneratedXml",
    "InvoiceEngine",
    "InvoiceLine",
    "InvoiceValidationError",
    "Party",
    "PintAeV1Engine",
    "UnknownSpecVersionError",
    "VatCategory",
    "available_spec_versions",
    "get_engine",
    "register_engine",
]
