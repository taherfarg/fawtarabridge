"""Invoice intake: canonical building, persistence, duplicate detection, lifecycle.

The supplier party is ALWAYS derived from the tenant's company profile — clients
cannot spoof their own supplier identity. Status here covers only DRAFT/VALIDATED;
the full state machine ships with the transmission layer (M4).
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorDetail, build_error_detail
from app.models import Contact, Invoice, Tenant
from app.pintae import CanonicalInvoice, get_engine
from app.pintae.canonical import Address, InvoiceLine, Party
from app.repositories.invoices import InvoiceRepository
from app.schemas.invoice import BuyerIn, InvoiceCreateIn

STATUS_DRAFT = "DRAFT"
STATUS_VALIDATED = "VALIDATED"
EDITABLE_STATUSES = (STATUS_DRAFT, STATUS_VALIDATED)

# Codes emitted via build_error_detail in this module (for the i18n catalog test).
SERVICE_ERROR_CODES: frozenset[str] = frozenset({"invoice.possible_duplicate"})


def supplier_party(tenant: Tenant) -> Party:
    return Party(
        name=tenant.legal_name_en,
        name_ar=tenant.legal_name_ar,
        trn=tenant.trn,
        address=Address(emirate=tenant.emirate, street=tenant.address, country_code="AE"),
    )


def _buyer_party(buyer: BuyerIn | None, contact: Contact | None) -> Party:
    if contact is not None:
        return Party(
            name=contact.name_en,
            name_ar=contact.name_ar,
            trn=contact.trn,
            peppol_id=contact.peppol_id,
            address=Address(
                street=contact.street,
                city=contact.city,
                emirate=contact.emirate,
                country_code=contact.country_code,
            ),
        )
    assert buyer is not None  # schema guarantees one of the two
    return Party(
        name=buyer.name,
        name_ar=buyer.name_ar,
        trn=buyer.trn,
        peppol_id=buyer.peppol_id,
        address=Address(
            street=buyer.street,
            city=buyer.city,
            emirate=buyer.emirate,
            country_code=buyer.country_code,
        ),
    )


def build_canonical(
    tenant: Tenant, payload: InvoiceCreateIn, contact: Contact | None
) -> CanonicalInvoice:
    lines = [
        InvoiceLine(
            line_id=line.line_id or str(index + 1),
            description=line.description,
            description_ar=line.description_ar,
            quantity=line.quantity,
            unit_code=line.unit_code,
            unit_price=line.unit_price,
            discount_amount=line.discount_amount,
            vat_category=line.vat_category,
            vat_rate=line.vat_rate,
            exemption_reason=line.exemption_reason,
            declared_net_amount=line.declared_net_amount,
            declared_vat_amount=line.declared_vat_amount,
        )
        for index, line in enumerate(payload.lines)
    ]
    return CanonicalInvoice(
        invoice_number=payload.invoice_number,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        note=payload.note,
        supplier=supplier_party(tenant),
        buyer=_buyer_party(payload.buyer, contact),
        lines=lines,
        declared_total_excluding_vat=payload.declared_total_excluding_vat,
        declared_total_vat=payload.declared_total_vat,
        declared_total_including_vat=payload.declared_total_including_vat,
    )


def duplicate_warnings(
    repo: InvoiceRepository,
    canonical: CanonicalInvoice,
    *,
    exclude_id: uuid.UUID | None = None,
) -> tuple[bool, list[ErrorDetail]]:
    engine = get_engine()
    totals = engine.totals(canonical)
    matches = repo.find_duplicates(
        buyer_trn=canonical.buyer.trn,
        buyer_name=canonical.buyer.name,
        total_including_vat=totals.tax_inclusive,
        issue_date=canonical.issue_date,
        exclude_id=exclude_id,
    )
    if not matches:
        return False, []
    numbers = ", ".join(m.invoice_number for m in matches[:5])
    return True, [build_error_detail("invoice.possible_duplicate", params={"matches": numbers})]


def _apply_denormalized(invoice: Invoice, canonical: CanonicalInvoice) -> None:
    engine = get_engine()
    invoice.canonical = canonical.model_dump(mode="json")
    invoice.issue_date = canonical.issue_date
    invoice.buyer_name = canonical.buyer.name
    invoice.buyer_trn = canonical.buyer.trn
    invoice.total_including_vat = engine.totals(canonical).tax_inclusive


def _translate_invoice_integrity_error(exc: IntegrityError) -> AppError:
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) or str(exc)
    if "uq_invoices_tenant_id" in constraint:
        return AppError("invoice.number_exists", status_code=409, field="invoice_number")
    raise exc


def create_invoice(
    db: Session,
    repo: InvoiceRepository,
    tenant: Tenant,
    canonical: CanonicalInvoice,
    *,
    contact_id: uuid.UUID | None,
    created_by: uuid.UUID,
) -> tuple[Invoice, list[ErrorDetail], list[ErrorDetail]]:
    """Persist as DRAFT regardless of rule errors (drafts may be incomplete);
    errors and duplicate warnings are returned alongside, never swallowed."""
    engine = get_engine()
    errors = engine.validate(canonical)
    is_duplicate, warnings = duplicate_warnings(repo, canonical)

    invoice = Invoice(
        invoice_number=canonical.invoice_number,
        status=STATUS_DRAFT,
        buyer_contact_id=contact_id,
        duplicate_warning=is_duplicate,
        created_by=created_by,
        canonical={},  # filled below
        issue_date=canonical.issue_date,
        buyer_name="",
        total_including_vat=0,
    )
    _apply_denormalized(invoice, canonical)
    repo.add(invoice)
    try:
        db.flush()
    except IntegrityError as exc:
        raise _translate_invoice_integrity_error(exc) from exc
    return invoice, errors, warnings


def update_invoice(
    db: Session,
    repo: InvoiceRepository,
    invoice: Invoice,
    canonical: CanonicalInvoice,
    *,
    contact_id: uuid.UUID | None,
) -> tuple[Invoice, list[ErrorDetail], list[ErrorDetail]]:
    if invoice.status not in EDITABLE_STATUSES:
        raise AppError("invoice.not_editable", status_code=409, params={"status": invoice.status})
    engine = get_engine()
    errors = engine.validate(canonical)
    is_duplicate, warnings = duplicate_warnings(repo, canonical, exclude_id=invoice.id)

    invoice.invoice_number = canonical.invoice_number
    invoice.buyer_contact_id = contact_id
    invoice.duplicate_warning = is_duplicate
    invoice.status = STATUS_DRAFT  # any edit re-opens the draft
    invoice.spec_version = None
    _apply_denormalized(invoice, canonical)
    try:
        db.flush()
    except IntegrityError as exc:
        raise _translate_invoice_integrity_error(exc) from exc
    return invoice, errors, warnings


def rehydrate(invoice: Invoice) -> CanonicalInvoice:
    return CanonicalInvoice.model_validate(invoice.canonical)


def validate_invoice(invoice: Invoice) -> list[ErrorDetail]:
    """Run the engine; flip DRAFT<->VALIDATED accordingly and pin the spec version."""
    engine = get_engine()
    errors = engine.validate(rehydrate(invoice))
    if errors:
        invoice.status = STATUS_DRAFT
        invoice.spec_version = None
    else:
        invoice.status = STATUS_VALIDATED
        invoice.spec_version = engine.spec_version
    return errors


def generate_xml(invoice: Invoice) -> bytes:
    """Engine refuses invalid invoices (InvoiceValidationError carries the report)."""
    engine = get_engine(invoice.spec_version) if invoice.spec_version else get_engine()
    result = engine.generate(rehydrate(invoice))
    invoice.spec_version = result.spec_version
    return result.xml
