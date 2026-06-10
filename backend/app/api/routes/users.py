from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import AuthDep, TenantDbDep, require_roles
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import TenantMembership, User
from app.models.enums import Role
from app.repositories.memberships import MembershipRepository
from app.schemas.user import MemberCreateIn, MemberOut, UserOut

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=UserOut)
def get_me(db: TenantDbDep, ctx: AuthDep) -> UserOut:
    user = db.get(User, ctx.user_id)
    if user is None:
        raise AppError("auth.not_authenticated", status_code=401)
    return UserOut.model_validate(user)


@router.get(
    "/tenants/me/members",
    response_model=list[MemberOut],
    dependencies=[Depends(require_roles(Role.OWNER, Role.ACCOUNTANT))],
)
def list_members(db: TenantDbDep, ctx: AuthDep) -> list[MemberOut]:
    repo = MembershipRepository(db, ctx.tenant_id)
    return [
        MemberOut(user=UserOut.model_validate(user), role=membership.role)
        for membership, user in repo.list_with_users()
    ]


@router.post(
    "/tenants/me/members",
    response_model=MemberOut,
    status_code=201,
    dependencies=[Depends(require_roles(Role.OWNER))],
)
def add_member(payload: MemberCreateIn, db: TenantDbDep, ctx: AuthDep) -> MemberOut:
    repo = MembershipRepository(db, ctx.tenant_id)

    user = db.scalars(select(User).where(User.email == payload.email.lower())).one_or_none()
    if user is None:
        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            phone=payload.phone,
        )
        db.add(user)
        db.flush()
    elif repo.get_by_user(user.id) is not None:
        raise AppError("member.already_exists", status_code=409, field="email")

    membership = repo.add(TenantMembership(user_id=user.id, role=payload.role))
    db.flush()
    return MemberOut(user=UserOut.model_validate(user), role=membership.role)
