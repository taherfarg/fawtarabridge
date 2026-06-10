"""Structural assertions on the UBL 2.1 output (xpath-level, beyond golden bytes)."""

from decimal import Decimal

from lxml import etree

from app.pintae.canonical import Party, VatCategory
from app.pintae.v1 import serializer
from tests.pintae_builders import make_invoice, make_line

NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def serialize_tree(invoice) -> etree._Element:
    return etree.fromstring(serializer.serialize(invoice))


def xp(tree: etree._Element, path: str) -> list:
    return tree.xpath(path, namespaces=NS)


def test_root_and_identifiers() -> None:
    tree = serialize_tree(make_invoice())
    assert tree.tag == f"{{{NS['inv']}}}Invoice"
    assert xp(tree, "cbc:CustomizationID/text()") == [serializer.CUSTOMIZATION_ID]
    assert xp(tree, "cbc:ProfileID/text()") == [serializer.PROFILE_ID]
    assert xp(tree, "cbc:ID/text()") == ["INV-1"]
    assert xp(tree, "cbc:InvoiceTypeCode/text()") == ["380"]
    assert xp(tree, "cbc:DocumentCurrencyCode/text()") == ["AED"]


def test_supplier_trn_lands_in_party_tax_scheme() -> None:
    tree = serialize_tree(make_invoice())
    trn = xp(
        tree,
        "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID/text()",
    )
    assert trn == ["100123456700001"]
    scheme = xp(
        tree,
        "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cac:TaxScheme/cbc:ID/text()",
    )
    assert scheme == ["VAT"]


def test_peppol_endpoint_id_scheme_split() -> None:
    invoice = make_invoice(
        supplier=Party(name="S", trn="100123456700001", peppol_id="0235:100123456700001")
    )
    tree = serialize_tree(invoice)
    endpoint = xp(tree, "cac:AccountingSupplierParty/cac:Party/cbc:EndpointID")[0]
    assert endpoint.text == "100123456700001"
    assert endpoint.get("schemeID") == "0235"


def test_arabic_party_name_emitted_as_additional_party_name() -> None:
    invoice = make_invoice(
        supplier=Party(name="Supplier LLC", name_ar="المورد ذ.م.م", trn="100123456700001")
    )
    tree = serialize_tree(invoice)
    names = xp(tree, "cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name/text()")
    assert names == ["Supplier LLC", "المورد ذ.م.م"]


def test_all_amounts_carry_currency_id() -> None:
    tree = serialize_tree(make_invoice())
    amounts = xp(tree, "//*[@currencyID]")
    assert amounts, "no amounts found"
    assert {el.get("currencyID") for el in amounts} == {"AED"}


def test_amount_formatting_two_decimals_percent_short_form() -> None:
    tree = serialize_tree(make_invoice(lines=[make_line(quantity="10", unit_price="100")]))
    assert xp(tree, "cac:TaxTotal/cbc:TaxAmount/text()") == ["50.00"]
    assert xp(tree, "cac:LegalMonetaryTotal/cbc:PayableAmount/text()") == ["1050.00"]
    assert xp(tree, "cac:InvoiceLine/cac:Item/cac:ClassifiedTaxCategory/cbc:Percent/text()") == [
        "5"
    ]


def test_line_discount_becomes_allowance_charge() -> None:
    invoice = make_invoice(
        lines=[make_line(quantity="3", unit_price="150.50", discount_amount="51.50")]
    )
    tree = serialize_tree(invoice)
    assert xp(tree, "cac:InvoiceLine/cac:AllowanceCharge/cbc:ChargeIndicator/text()") == ["false"]
    assert xp(tree, "cac:InvoiceLine/cac:AllowanceCharge/cbc:Amount/text()") == ["51.50"]
    assert xp(tree, "cac:InvoiceLine/cbc:LineExtensionAmount/text()") == ["400.00"]
    # No discount → no AllowanceCharge element at all
    plain = serialize_tree(make_invoice())
    assert xp(plain, "cac:InvoiceLine/cac:AllowanceCharge") == []


def test_exemption_reason_emitted_on_tax_category() -> None:
    invoice = make_invoice(
        lines=[
            make_line(
                vat_category=VatCategory.EXEMPT,
                vat_rate="0",
                exemption_reason="Exempt — Article 42",
            )
        ]
    )
    tree = serialize_tree(invoice)
    reasons = xp(tree, "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReason/text()")
    assert reasons == ["Exempt — Article 42"]


def test_arabic_line_description_emitted_as_item_description() -> None:
    invoice = make_invoice(
        lines=[make_line(description="Oak desk", description_ar="مكتب من خشب البلوط")]
    )
    tree = serialize_tree(invoice)
    assert xp(tree, "cac:InvoiceLine/cac:Item/cbc:Description/text()") == ["مكتب من خشب البلوط"]
    assert xp(tree, "cac:InvoiceLine/cac:Item/cbc:Name/text()") == ["Oak desk"]


def test_quantity_formatting_preserves_decimals_without_exponent() -> None:
    invoice = make_invoice(lines=[make_line(quantity="2.50", unit_price="10")])
    tree = serialize_tree(invoice)
    qty = xp(tree, "cac:InvoiceLine/cbc:InvoicedQuantity")[0]
    assert qty.text == "2.5"
    assert qty.get("unitCode") == "C62"


def test_tax_subtotals_one_per_category_sorted() -> None:
    invoice = make_invoice(
        lines=[
            make_line(line_id="1", quantity="1", unit_price="100"),
            make_line(
                line_id="2",
                quantity="1",
                unit_price="100",
                vat_category=VatCategory.ZERO_RATED,
                vat_rate="0",
            ),
            make_line(line_id="3", quantity="2", unit_price="100"),
        ]
    )
    tree = serialize_tree(invoice)
    ids = xp(tree, "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:ID/text()")
    assert ids == ["S", "Z"]
    taxable = xp(tree, "cac:TaxTotal/cac:TaxSubtotal/cbc:TaxableAmount/text()")
    assert taxable == ["300.00", "100.00"]


def test_unit_price_precision_is_never_silently_rounded() -> None:
    invoice = make_invoice(lines=[make_line(quantity="1", unit_price="0.105")])
    tree = serialize_tree(invoice)
    assert xp(tree, "cac:InvoiceLine/cac:Price/cbc:PriceAmount/text()") == ["0.105"]
    # …while plain prices still get the canonical 2-decimal form.
    plain = serialize_tree(make_invoice(lines=[make_line(unit_price="100")]))
    assert xp(plain, "cac:InvoiceLine/cac:Price/cbc:PriceAmount/text()") == ["100.00"]


def test_percent_with_decimals_keeps_fraction() -> None:
    assert serializer._percent(Decimal("5")) == "5"
    assert serializer._percent(Decimal("5.00")) == "5"
    assert serializer._percent(Decimal("2.5")) == "2.5"
    assert serializer._percent(Decimal("0")) == "0"
