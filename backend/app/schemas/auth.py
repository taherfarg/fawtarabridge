import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role
from app.schemas.common import PasswordStr, PhoneStr
from app.schemas.tenant import CompanyIn, TenantOut
from app.schemas.user import UserOut


class SignupIn(BaseModel):
    email: EmailStr
    password: PasswordStr
    full_name: str = Field(min_length=1, max_length=255)
    phone: PhoneStr
    company: CompanyIn


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MembershipOut(BaseModel):
    tenant_id: uuid.UUID
    role: Role


class SignupOut(BaseModel):
    user: UserOut
    tenant: TenantOut
    tokens: TokenPairOut


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginOut(BaseModel):
    user: UserOut
    tokens: TokenPairOut
    active_tenant_id: uuid.UUID
    memberships: list[MembershipOut]


class RefreshIn(BaseModel):
    refresh_token: str


class SwitchTenantIn(BaseModel):
    tenant_id: uuid.UUID


class OtpVerifyIn(BaseModel):
    code: str = Field(min_length=4, max_length=10)
