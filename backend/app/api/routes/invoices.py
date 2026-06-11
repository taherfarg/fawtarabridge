import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from app.api.deps import AuthContext, AuthDep, TenantDbDep, require_roles
from app.core.errors import AppError
from app.models import Contact, Invoice, Tenant
from app.models.enums import Role
from app.pintae import InvoiceValidationError, get_engine
from app.repositories.contacts import ContactRepository
from app.repositories.invoices import InvoiceRepository
from app.schemas.invoice import (
    InvoiceCreateIn,
    InvoiceCreateOut,
    InvoiceDetailOut,
    InvoiceListOut,
    InvoiceOut,
    ValidationReportOut,
)
from app.services import invoice_service

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
    return InvoiceDetailOut(
        **InvoiceOut.model_validate(invoice).model_dump(),
        canonical=canonical,
        errors=errors,
        warnings=warnings,
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
        db, repo, invoice, canonical, contact_id=payload.buyer_contact_id
    )
    return InvoiceCreateOut(
        invoice=InvoiceOut.model_validate(invoice), errors=errors, warnings=warnings
    )


@router.post("/{invoice_id}/validate", response_model=ValidationReportOut)
def validate_invoice(invoice_id: uuid.UUID, db: TenantDbDep, ctx: WriteCtx) -> ValidationReportOut:
    repo = InvoiceRepository(db, ctx.tenant_id)
    invoice = _get_or_404(repo, invoice_id)
    errors = invoice_service.validate_invoice(invoice)
    _, warnings = invoice_service.duplicate_warnings(
        repo, invoice_service.rehydrate(invoice), exclude_id=invoice.id
    )
    return ValidationReportOut(
        status=invoice.status,
        spec_version=invoice.spec_version,
        errors=errors,
        warnings=warnings,
    )


@router.get("/{invoice_id}/xml")
def download_xml(invoice_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep) -> Response:
    invoice = _get_or_404(InvoiceRepository(db, ctx.tenant_id), invoice_id)
    try:
        xml = invoice_service.generate_xml(invoice)
    except InvoiceValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={"errors": [e.model_dump() for e in exc.errors]},
        )
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.xml"'},
    )
