from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import AuthDep, DbDep, TenantDbDep
from app.core.rate_limit import enforce_auth_rate_limit
from app.schemas.auth import (
    LoginIn,
    LoginOut,
    MembershipOut,
    OtpVerifyIn,
    RefreshIn,
    SignupIn,
    SignupOut,
    SwitchTenantIn,
    TokenPairOut,
)
from app.schemas.tenant import TenantOut
from app.schemas.user import UserOut
from app.services import auth_service
from app.services.otp import OTPProvider, get_otp_provider

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(enforce_auth_rate_limit)])

OtpProviderDep = Annotated[OTPProvider, Depends(get_otp_provider)]


@router.post("/signup", response_model=SignupOut, status_code=201)
def signup(payload: SignupIn, db: DbDep, otp_provider: OtpProviderDep) -> SignupOut:
    user, tenant, tokens = auth_service.signup(db, payload, otp_provider)
    return SignupOut(
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
        tokens=tokens,
    )


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: DbDep) -> LoginOut:
    user, tokens, active_tenant_id, memberships = auth_service.login(
        db, payload.email, payload.password
    )
    return LoginOut(
        user=UserOut.model_validate(user),
        tokens=tokens,
        active_tenant_id=active_tenant_id,
        memberships=[MembershipOut(tenant_id=m.tenant_id, role=m.role) for m in memberships],
    )


@router.post("/refresh", response_model=TokenPairOut)
def refresh(payload: RefreshIn, db: DbDep) -> TokenPairOut:
    return auth_service.refresh_tokens(db, payload.refresh_token)


@router.post("/logout", status_code=204)
def logout(payload: RefreshIn, db: DbDep) -> None:
    auth_service.logout(db, payload.refresh_token)


@router.post("/switch-tenant", response_model=TokenPairOut)
def switch_tenant(payload: SwitchTenantIn, db: DbDep, ctx: AuthDep) -> TokenPairOut:
    return auth_service.switch_tenant(db, ctx.user_id, payload.tenant_id)


@router.post("/otp/request", status_code=204)
def request_otp(db: TenantDbDep, ctx: AuthDep, otp_provider: OtpProviderDep) -> None:
    auth_service.request_otp(db, ctx.user_id, otp_provider)


@router.post("/otp/verify", status_code=204)
def verify_otp(payload: OtpVerifyIn, db: TenantDbDep, ctx: AuthDep) -> None:
    auth_service.verify_otp(db, ctx.user_id, payload.code)
