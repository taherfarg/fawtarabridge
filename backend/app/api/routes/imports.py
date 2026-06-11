import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import AuthContext, AuthDep, TenantDbDep, require_roles
from app.core.errors import AppError
from app.models import ImportMappingTemplate, Tenant
from app.models.enums import Role
from app.repositories.templates import MappingTemplateRepository
from app.schemas.importing import (
    ImportReportOut,
    ImportRequestMeta,
    MappingTemplateIn,
    MappingTemplateOut,
)
from app.services.import_service import run_import

router = APIRouter(tags=["import"])

WriteCtx = Annotated[AuthContext, Depends(require_roles(Role.OWNER, Role.ACCOUNTANT, Role.STAFF))]


def _parse_meta(payload: str) -> ImportRequestMeta:
    try:
        return ImportRequestMeta.model_validate_json(payload)
    except ValidationError as exc:
        # Same bilingual 422 envelope as body validation everywhere else.
        raise RequestValidationError(exc.errors()) from exc


async def _do_import(
    db: TenantDbDep, ctx: AuthContext, file: UploadFile, payload: str, *, persist: bool
) -> ImportReportOut:
    meta = _parse_meta(payload)
    tenant = db.get(Tenant, ctx.tenant_id)
    assert tenant is not None
    content = await file.read()
    return run_import(
        db,
        tenant,
        user_id=ctx.user_id,
        filename=file.filename or "",
        content=content,
        meta=meta,
        persist=persist,
    )


@router.post("/invoices/import/preview", response_model=ImportReportOut)
async def preview_import(
    db: TenantDbDep,
    ctx: WriteCtx,
    file: Annotated[UploadFile, File()],
    payload: Annotated[str, Form()],
) -> ImportReportOut:
    return await _do_import(db, ctx, file, payload, persist=False)


@router.post("/invoices/import/commit", response_model=ImportReportOut)
async def commit_import(
    db: TenantDbDep,
    ctx: WriteCtx,
    file: Annotated[UploadFile, File()],
    payload: Annotated[str, Form()],
) -> ImportReportOut:
    return await _do_import(db, ctx, file, payload, persist=True)


@router.get("/import/templates", response_model=list[MappingTemplateOut])
def list_templates(db: TenantDbDep, ctx: AuthDep) -> list[MappingTemplateOut]:
    templates = MappingTemplateRepository(db, ctx.tenant_id).list_all()
    return [MappingTemplateOut.model_validate(t) for t in templates]


@router.post("/import/templates", response_model=MappingTemplateOut, status_code=201)
def create_template(
    payload: MappingTemplateIn, db: TenantDbDep, ctx: WriteCtx
) -> MappingTemplateOut:
    repo = MappingTemplateRepository(db, ctx.tenant_id)
    if repo.get_by_name(payload.name) is not None:
        raise AppError("import.template_name_exists", status_code=409, field="name")
    template = repo.add(
        ImportMappingTemplate(name=payload.name, mapping=payload.mapping.model_dump(mode="json"))
    )
    db.flush()
    return MappingTemplateOut.model_validate(template)


@router.delete("/import/templates/{template_id}", status_code=204)
def delete_template(template_id: uuid.UUID, db: TenantDbDep, ctx: WriteCtx) -> None:
    repo = MappingTemplateRepository(db, ctx.tenant_id)
    template = repo.get(template_id)
    if template is None:
        raise AppError("import.template_not_found", status_code=404)
    db.delete(template)
