import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Role
from app.schemas.common import PasswordStr, PhoneStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: str
    phone_verified: bool


class MemberCreateIn(BaseModel):
    """Adds a member to the current tenant.

    If the email already belongs to an existing identity (e.g. an accountant on
    other tenants), only the membership is created — name/phone/password inputs
    are ignored to prevent account takeover via invite.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    phone: PhoneStr
    password: PasswordStr
    role: Role


class MemberOut(BaseModel):
    user: UserOut
    role: Role


class MemberRoleIn(BaseModel):
    role: Role
