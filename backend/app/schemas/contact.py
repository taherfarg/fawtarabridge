import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.pintae.canonical import VatCategory
from app.schemas.common import PhoneStr, TrnStr


class ContactIn(BaseModel):
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str | None = Field(default=None, max_length=255)
    trn: TrnStr | None = None
    peppol_id: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: PhoneStr | None = None
    street: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    emirate: str | None = Field(default=None, max_length=50)
    country_code: str = Field(default="AE", min_length=2, max_length=2)
    default_vat_category: VatCategory | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name_en: str
    name_ar: str | None
    trn: str | None
    peppol_id: str | None
    email: str | None
    phone: str | None
    street: str | None
    city: str | None
    emirate: str | None
    country_code: str
    default_vat_category: VatCategory | None


class ContactListOut(BaseModel):
    items: list[ContactOut]
    total: int
    limit: int
    offset: int
