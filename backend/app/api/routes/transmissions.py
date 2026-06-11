from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import AuthContext, TenantDbDep, require_roles
from app.models.enums import Role
from app.repositories.transmissions import TransmissionRepository
from app.schemas.transmission import TransmissionOut

router = APIRouter(prefix="/transmissions", tags=["transmissions"])

AdminCtx = Annotated[AuthContext, Depends(require_roles(Role.OWNER, Role.ACCOUNTANT))]


@router.get("/dead-letter", response_model=list[TransmissionOut])
def dead_letter_queue(db: TenantDbDep, ctx: AdminCtx) -> list[TransmissionOut]:
    """Transmissions that exhausted retries or failed permanently (FR-4.2 admin
    visibility). Recovery: fix the invoice (PUT) or POST /invoices/{id}/resend."""
    rows = TransmissionRepository(db, ctx.tenant_id).list_needing_attention()
    return [TransmissionOut.from_model(t) for t in rows]
