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


@router.post(
    "/me/onboard-asp",
    response_model=TenantOut,
    status_code=202,
    dependencies=[Depends(require_roles(Role.OWNER))],
)
def onboard_asp(db: TenantDbDep, ctx: AuthDep) -> TenantOut:
    """Start Peppol participant registration via the ASP (FR-1.3). Asynchronous —
    the worker updates asp_onboarding_status; the UI polls GET /tenants/me."""
    from app.services import audit_service
    from app.worker.tasks import register_participant

    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise AppError("tenant.not_found", status_code=404)
    if tenant.asp_onboarding_status in ("pending", "registered"):
        raise AppError("tenant.asp_already_registered", status_code=409)

    before = tenant.asp_onboarding_status
    tenant.asp_onboarding_status = "pending"
    audit_service.record(
        db,
        tenant.id,
        action="tenant.asp_onboarding_requested",
        entity_type="tenant",
        entity_id=tenant.id,
        actor_id=ctx.user_id,
        before={"status": before},
        after={"status": "pending"},
    )
    out = TenantOut.model_validate(tenant)
    db.commit()  # worker session must see the pending row (eager mode runs inline)
    register_participant.delay(str(tenant.id))
    return out
