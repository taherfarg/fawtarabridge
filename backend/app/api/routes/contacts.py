import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError

from app.api.deps import AuthContext, AuthDep, TenantDbDep, require_roles
from app.core.errors import AppError
from app.models import Contact
from app.models.enums import Role
from app.repositories.contacts import ContactRepository
from app.schemas.contact import ContactIn, ContactListOut, ContactOut

router = APIRouter(prefix="/contacts", tags=["contacts"])

WriteCtx = Annotated[AuthContext, Depends(require_roles(Role.OWNER, Role.ACCOUNTANT, Role.STAFF))]


def _get_or_404(repo: ContactRepository, contact_id: uuid.UUID) -> Contact:
    contact = repo.get(contact_id)
    if contact is None:
        raise AppError("contact.not_found", status_code=404)
    return contact


def _flush_translating_trn_conflict(repo: ContactRepository) -> None:
    try:
        repo.session.flush()
    except IntegrityError as exc:
        diag = getattr(exc.orig, "diag", None)
        constraint = getattr(diag, "constraint_name", None) or str(exc)
        if "trn" in constraint:
            raise AppError("contact.trn_exists", status_code=409, field="trn") from exc
        raise


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactIn, db: TenantDbDep, ctx: WriteCtx) -> ContactOut:
    repo = ContactRepository(db, ctx.tenant_id)
    contact = repo.add(Contact(**payload.model_dump()))
    _flush_translating_trn_conflict(repo)
    return ContactOut.model_validate(contact)


@router.get("", response_model=ContactListOut)
def list_contacts(
    db: TenantDbDep,
    ctx: AuthDep,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ContactListOut:
    items, total = ContactRepository(db, ctx.tenant_id).search(search, limit=limit, offset=offset)
    return ContactListOut(
        items=[ContactOut.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: uuid.UUID, db: TenantDbDep, ctx: AuthDep) -> ContactOut:
    return ContactOut.model_validate(_get_or_404(ContactRepository(db, ctx.tenant_id), contact_id))


@router.put("/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: uuid.UUID, payload: ContactIn, db: TenantDbDep, ctx: WriteCtx
) -> ContactOut:
    repo = ContactRepository(db, ctx.tenant_id)
    contact = _get_or_404(repo, contact_id)
    for field, value in payload.model_dump().items():
        setattr(contact, field, value)
    _flush_translating_trn_conflict(repo)
    return ContactOut.model_validate(contact)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: uuid.UUID, db: TenantDbDep, ctx: WriteCtx) -> None:
    repo = ContactRepository(db, ctx.tenant_id)
    contact = _get_or_404(repo, contact_id)
    db.delete(contact)
