import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import AuthContext, AuthDep, TenantDbDep, require_roles
from app.core.errors import AppError
from app.models import Contact, Invoice, Tenant
from app.models.enums import Role
from app.pintae import get_engine
from app.repositories.contacts import ContactRepository
from app.repositories.invoices import InvoiceRepository
from app.repositories.transmissions import TransmissionRepository
from app.schemas.invoice import (
    InvoiceCreateIn,
    InvoiceCreateOut,
    InvoiceDetailOut,
    InvoiceListOut,
    InvoiceOut,
    ValidationReportOut,
)
from app.schemas.transmission import AuditEventOut, SendOut, TransmissionOut
from app.services import audit_service, invoice_service, transmission_service
from app.worker.tasks import transmit_invoice

router = APIRouter(prefix="/invoices", tags=["invoices"])

WriteCtx = Annotated[AuthContext, Depends(require_roles(Role.OWNER, Role.ACCOUNTANT, Role.STAFF))]


def _get_or_404(repo: InvoiceRepository, invoice_id: uuid.UUID) -> Invoice:
    invoice = repo.get(invoice_id)
    if invoice is None:
        raise AppError("invoice.not_found", status_code=404)
    return invoice


def _tenant(db: TenantDbDep, ctx: AuthContext) -> Tenant:
    tenant = db.get(Tenant, ctx.tenant_id)
    assert tenant is not None  # token references it; RLS tenant arm exposes it
    return tenant


def _contact_or_404(db: TenantDbDep, ctx: AuthContext, payload: InvoiceCreateIn) -> Contact | None:
    if payload.buyer_contact_id is None:
        return None
    contact = ContactRepository(db, ctx.tenant_id).get(payload.buyer_contact_id)
    if contact is None:
        raise AppError("contact.not_found", status_code=404, field="buyer_contact_id")
    return contact


@router.post("", response_model=InvoiceCreateOut, status_code=201)
def create_invoice(payload: InvoiceCreateIn, db: TenantDbDep, ctx: WriteCtx) -> InvoiceCreateOut:
    tenant = _tenant(db, ctx)
    contact = _contact_or_404(db, ctx, payload)
    canonical = invoice_service.build_canonical(tenant, payload, contact)
    invoice, errors, warnings = invoice_service.create_invoice(
        db,
        InvoiceRepository(db, ctx.tenant_id),
        tenant,
        canonical,
        contact_id=payload.buyer_contact_id,
        created_by=ctx.user_id,
    )
    return InvoiceCreateOut(
        invoice=InvoiceOut.model_validate(invoice), errors=errors, warnings=warnings
    )


@router.get("", response_model=InvoiceListOut)
def list_invoices(
    db: TenantDbDep,
    ctx: AuthDep,
    status: str | None = Query(default=None, max_length=20),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    buyer: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> InvoiceListOut:
    items, total = InvoiceRepository(db, ctx.tenant_id).list_filtered(
        status=status,
        date_from=date_from,
        date_to=date_to,
        buyer=buyer,
        limit=limit,
        offset=offset,
    )
    return InvoiceListOut(
        items=[InvoiceOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(invoice_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep) -> InvoiceDetailOut:
    repo = InvoiceRepository(db, ctx.tenant_id)
    invoice = _get_or_404(repo, invoice_id)
    canonical = invoice_service.rehydrate(invoice)
    errors = get_engine().validate(canonical)
    _, warnings = invoice_service.duplicate_warnings(repo, canonical, exclude_id=invoice.id)
    transmissions = TransmissionRepository(db, ctx.tenant_id).list_for_invoice(invoice.id)
    latest = (
        TransmissionOut.from_model(transmissions[0]).model_dump(mode="json")
        if transmissions
        else None
    )
    return InvoiceDetailOut(
        **InvoiceOut.model_validate(invoice).model_dump(),
        canonical=canonical,
        errors=errors,
        warnings=warnings,
        latest_transmission=latest,
    )


@router.put("/{invoice_id}", response_model=InvoiceCreateOut)
def update_invoice(
    invoice_id: uuid.UUID, payload: InvoiceCreateIn, db: TenantDbDep, ctx: WriteCtx
) -> InvoiceCreateOut:
    tenant = _tenant(db, ctx)
    repo = InvoiceRepository(db, ctx.tenant_id)
    invoice = _get_or_404(repo, invoice_id)
    contact = _contact_or_404(db, ctx, payload)
    canonical = invoice_service.build_canonical(tenant, payload, contact)
    invoice, errors, warnings = invoice_service.update_invoice(
        db, repo, invoice, canonical, contact_id=payload.buyer_contact_id, actor_id=ctx.user_id
    )
    return InvoiceCreateOut(
        invoice=InvoiceOut.model_validate(invoice), errors=errors, warnings=warnings
    )


@router.post("/{invoice_id}/validate", response_model=ValidationReportOut)
def validate_invoice(invoice_id: uuid.UUID, db: TenantDbDep, ctx: WriteCtx) -> ValidationReportOut:
    repo = InvoiceRepository(db, ctx.tenant_id)
    invoice = _get_or_404(repo, invoice_id)
    errors = invoice_service.validate_invoice(db, invoice, actor_id=ctx.user_id)
    _, warnings = invoice_service.duplicate_warnings(
        repo, invoice_service.rehydrate(invoice), exclude_id=invoice.id
    )
    return ValidationReportOut(
        status=invoice.status,
        spec_version=invoice.spec_version,
        errors=errors,
        warnings=warnings,
    )


def _queue_and_dispatch(
    db: TenantDbDep, ctx: AuthContext, invoice: Invoice, *, resend: bool
) -> SendOut:
    transmission = transmission_service.queue_transmission(
        db, invoice, actor_id=ctx.user_id, resend=resend
    )
    out = SendOut(
        invoice_id=invoice.id,
        invoice_status=invoice.status,
        transmission=TransmissionOut.from_model(transmission),
    )
    # Commit BEFORE enqueueing: the worker opens its own session and must see the
    # row (in eager test mode the task runs inline right here).
    db.commit()
    transmit_invoice.delay(str(transmission.id), str(ctx.tenant_id))
    return out


@router.post("/{invoice_id}/send", response_model=SendOut, status_code=202)
def send_invoice(invoice_id: uuid.UUID, db: TenantDbDep, ctx: WriteCtx) -> SendOut:
    """Queue transmission to the ASP (architecture rule 4: never synchronous)."""
    invoice = _get_or_404(InvoiceRepository(db, ctx.tenant_id), invoice_id)
    return _queue_and_dispatch(db, ctx, invoice, resend=False)


@router.post("/{invoice_id}/resend", response_model=SendOut, status_code=202)
def resend_invoice(invoice_id: uuid.UUID, db: TenantDbDep, ctx: WriteCtx) -> SendOut:
    """Re-queue a REJECTED/ERROR invoice unchanged (fix-and-resend goes via PUT)."""
    invoice = _get_or_404(InvoiceRepository(db, ctx.tenant_id), invoice_id)
    return _queue_and_dispatch(db, ctx, invoice, resend=True)


@router.get("/{invoice_id}/audit", response_model=list[AuditEventOut])
def invoice_audit_trail(
    invoice_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep
) -> list[AuditEventOut]:
    _get_or_404(InvoiceRepository(db, ctx.tenant_id), invoice_id)
    events = audit_service.list_for_entity(
        db, ctx.tenant_id, entity_type="invoice", entity_id=invoice_id
    )
    return [AuditEventOut.model_validate(e) for e in events]


@router.get("/{invoice_id}/transmissions", response_model=list[TransmissionOut])
def invoice_transmissions(
    invoice_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep
) -> list[TransmissionOut]:
    _get_or_404(InvoiceRepository(db, ctx.tenant_id), invoice_id)
    rows = TransmissionRepository(db, ctx.tenant_id).list_for_invoice(invoice_id)
    return [TransmissionOut.from_model(t) for t in rows]


@router.get("/{invoice_id}/xml")
def download_xml(invoice_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep) -> Response:
    invoice = _get_or_404(InvoiceRepository(db, ctx.tenant_id), invoice_id)
    xml = invoice_service.generate_xml(invoice)  # InvoiceValidationError -> 422 envelope
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.xml"'},
    )
