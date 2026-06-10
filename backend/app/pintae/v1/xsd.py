"""Structural validation against the vendored OASIS UBL 2.1 Invoice schema.

This is a self-check on the serializer (and a guard against future regressions),
complementing — not replacing — the business rules. The official PINT-AE
Schematron, once published, will slot in next to this.
"""

from functools import lru_cache
from pathlib import Path

import xmlschema

XSD_PATH = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "xsd"
    / "ubl-2.1"
    / "maindoc"
    / "UBL-Invoice-2.1.xsd"
)


@lru_cache
def get_invoice_schema() -> xmlschema.XMLSchema:
    return xmlschema.XMLSchema(str(XSD_PATH))


def xsd_errors(xml: bytes) -> list[str]:
    """Return human-readable schema violations (empty list = structurally valid)."""
    schema = get_invoice_schema()
    return [
        f"{error.reason} (at {error.path})" if error.path else str(error.reason)
        for error in schema.iter_errors(xml.decode("utf-8"))
    ]
