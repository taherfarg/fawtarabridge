from fastapi import APIRouter, Query

from app.api.deps import AuthDep, TenantDbDep
from app.schemas.archive import ComplianceSummaryOut
from app.services import compliance_service

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("/summary", response_model=ComplianceSummaryOut)
def compliance_summary(
    db: TenantDbDep,
    ctx: AuthDep,
    period: str | None = Query(default=None, description="YYYY-MM; defaults to current month"),
) -> ComplianceSummaryOut:
    return ComplianceSummaryOut(**compliance_service.monthly_summary(db, ctx.tenant_id, period))
