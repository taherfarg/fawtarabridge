from fastapi import APIRouter, Depends

from app.api.deps import AuthDep, TenantDbDep, require_roles
from app.core.errors import AppError
from app.models import Tenant
from app.models.enums import Role
from app.schemas.tenant import TenantOut, TenantUpdateIn

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/me", response_model=TenantOut)
def get_my_tenant(db: TenantDbDep, ctx: AuthDep) -> TenantOut:
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:  # only possible if the tenant was deleted mid-session
        raise AppError("tenant.not_found", status_code=404)
    return TenantOut.model_validate(tenant)


@router.patch(
    "/me",
    response_model=TenantOut,
    dependencies=[Depends(require_roles(Role.OWNER))],
)
def update_my_tenant(payload: TenantUpdateIn, db: TenantDbDep, ctx: AuthDep) -> TenantOut:
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise AppError("tenant.not_found", status_code=404)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    return TenantOut.model_validate(tenant)
