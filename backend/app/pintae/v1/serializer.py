"""UBL 2.1 Invoice serializer for spec v1 (PINT-AE conventions).

Output is deterministic (fixed element order, 2-decimal amount formatting,
pretty-printed UTF-8) so golden-file tests can compare bytes.

The serializer assumes the invoice passed rule validation; it performs no
correction of its own. Structural correctness is additionally cross-checked by
the vendored OASIS UBL 2.1 XSD in tests.
"""

from decimal import Decimal

from lxml import etree

from app.pintae.canonical import CanonicalInvoice, InvoiceLine, Party
from app.pintae.v1.calc import compute_totals, decimal_places, line_net

INV_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NSMAP = {None: INV_NS, "cac": CAC, "cbc": CBC}

# SPEC-CHECK: PINT-AE customization/profile identifiers. "billing-1@ae-1" follows
# the published Peppol PINT specialization pattern; confirm the exact values against
# the official MoF / OpenPeppol PINT-AE release and the ASP's requirements.
CUSTOMIZATION_ID = "urn:peppol:pint:billing-1@ae-1"
PROFILE_ID = "urn:peppol:bis:billing"

TAX_SCHEME_VAT = "VAT"


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _price(value: Decimal) -> str:
    """Unit prices keep their full given precision (min 2 decimals) — rounding a
    price the customer entered would silently change their data. Monetary totals
    stay strictly 2-decimal (# SPEC-CHECK: EN 16931 allows extra precision only
    for the unit price; confirm PINT-AE carries that rule over)."""
    if decimal_places(value) <= 2:
        return f"{value:.2f}"
    return format(value.normalize(), "f")


def _percent(rate: Decimal) -> str:
    # SPEC-CHECK: percent formatting — emit the canonical short form ("5", "2.5").
    text = format(rate.normalize(), "f")
    return text


def _quantity(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _el(parent: etree._Element, ns: str, tag: str, text: str | None = None) -> etree._Element:
    el = etree.SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _amount_el(parent: etree._Element, tag: str, value: Decimal, currency: str) -> etree._Element:
    el = _el(parent, CBC, tag, _amount(value))
    el.set("currencyID", currency)
    return el


def _party(parent: etree._Element, tag: str, party: Party) -> None:
    wrapper = _el(parent, CAC, tag)
    el_party = _el(wrapper, CAC, "Party")

    if party.peppol_id:
        scheme, _, identifier = party.peppol_id.partition(":")
        endpoint = _el(el_party, CBC, "EndpointID", identifier if identifier else scheme)
        if identifier:
            endpoint.set("schemeID", scheme)

    name_el = _el(el_party, CAC, "PartyName")
    _el(name_el, CBC, "Name", party.name)
    if party.name_ar:
        # SPEC-CHECK: Arabic name carried as an additional PartyName. Confirm how
        # PINT-AE expects bilingual party names (additional PartyName vs. extension).
        name_ar_el = _el(el_party, CAC, "PartyName")
        _el(name_ar_el, CBC, "Name", party.name_ar)

    address = _el(el_party, CAC, "PostalAddress")
    if party.address.street:
        _el(address, CBC, "StreetName", party.address.street)
    if party.address.city:
        _el(address, CBC, "CityName", party.address.city)
    if party.address.emirate:
        _el(address, CBC, "CountrySubentity", party.address.emirate)
    country = _el(address, CAC, "Country")
    _el(country, CBC, "IdentificationCode", party.address.country_code)

    tax_scheme_wrap = _el(el_party, CAC, "PartyTaxScheme")
    _el(tax_scheme_wrap, CBC, "CompanyID", party.trn or "")
    scheme_el = _el(tax_scheme_wrap, CAC, "TaxScheme")
    _el(scheme_el, CBC, "ID", TAX_SCHEME_VAT)

    legal = _el(el_party, CAC, "PartyLegalEntity")
    _el(legal, CBC, "RegistrationName", party.name)


def _invoice_line(parent: etree._Element, line: InvoiceLine, currency: str) -> None:
    el_line = _el(parent, CAC, "InvoiceLine")
    _el(el_line, CBC, "ID", line.line_id)
    qty = _el(el_line, CBC, "InvoicedQuantity", _quantity(line.quantity))
    qty.set("unitCode", line.unit_code)
    _amount_el(el_line, "LineExtensionAmount", line_net(line), currency)

    if line.discount_amount > 0:
        allowance = _el(el_line, CAC, "AllowanceCharge")
        _el(allowance, CBC, "ChargeIndicator", "false")
        _el(allowance, CBC, "AllowanceChargeReason", "Discount")
        _amount_el(allowance, "Amount", line.discount_amount, currency)

    item = _el(el_line, CAC, "Item")
    if line.description_ar:
        # SPEC-CHECK: Arabic line description as cbc:Description; confirm against
        # the PINT-AE bilingual content guidance.
        _el(item, CBC, "Description", line.description_ar)
    _el(item, CBC, "Name", line.description)
    tax_cat = _el(item, CAC, "ClassifiedTaxCategory")
    _el(tax_cat, CBC, "ID", line.vat_category.value)
    _el(tax_cat, CBC, "Percent", _percent(line.vat_rate))
    scheme = _el(tax_cat, CAC, "TaxScheme")
    _el(scheme, CBC, "ID", TAX_SCHEME_VAT)

    price = _el(el_line, CAC, "Price")
    price_el = _el(price, CBC, "PriceAmount", _price(line.unit_price))
    price_el.set("currencyID", currency)


def serialize(invoice: CanonicalInvoice) -> bytes:
    currency = invoice.currency
    totals = compute_totals(invoice)

    # lxml accepts None as the default-namespace key; the stubs type it too narrowly.
    root = etree.Element(f"{{{INV_NS}}}Invoice", nsmap=NSMAP)  # type: ignore[arg-type]
    _el(root, CBC, "CustomizationID", CUSTOMIZATION_ID)
    _el(root, CBC, "ProfileID", PROFILE_ID)
    _el(root, CBC, "ID", invoice.invoice_number)
    _el(root, CBC, "IssueDate", invoice.issue_date.isoformat())
    if invoice.due_date is not None:
        _el(root, CBC, "DueDate", invoice.due_date.isoformat())
    _el(root, CBC, "InvoiceTypeCode", invoice.invoice_type_code)
    if invoice.note:
        _el(root, CBC, "Note", invoice.note)
    _el(root, CBC, "DocumentCurrencyCode", currency)

    _party(root, "AccountingSupplierParty", invoice.supplier)
    _party(root, "AccountingCustomerParty", invoice.buyer)

    tax_total = _el(root, CAC, "TaxTotal")
    _amount_el(tax_total, "TaxAmount", totals.tax_total, currency)
    for cat in totals.by_category:
        subtotal = _el(tax_total, CAC, "TaxSubtotal")
        _amount_el(subtotal, "TaxableAmount", cat.taxable, currency)
        _amount_el(subtotal, "TaxAmount", cat.tax, currency)
        category_el = _el(subtotal, CAC, "TaxCategory")
        _el(category_el, CBC, "ID", cat.category.value)
        _el(category_el, CBC, "Percent", _percent(cat.rate))
        if cat.exemption_reason:
            _el(category_el, CBC, "TaxExemptionReason", cat.exemption_reason)
        scheme = _el(category_el, CAC, "TaxScheme")
        _el(scheme, CBC, "ID", TAX_SCHEME_VAT)

    monetary = _el(root, CAC, "LegalMonetaryTotal")
    _amount_el(monetary, "LineExtensionAmount", totals.line_extension, currency)
    _amount_el(monetary, "TaxExclusiveAmount", totals.tax_exclusive, currency)
    _amount_el(monetary, "TaxInclusiveAmount", totals.tax_inclusive, currency)
    _amount_el(monetary, "PayableAmount", totals.payable, currency)

    for line in invoice.lines:
        _invoice_line(root, line, currency)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
