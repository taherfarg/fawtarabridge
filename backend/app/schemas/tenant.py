import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RevenueBand
from app.schemas.common import TrnStr


class CompanyIn(BaseModel):
    legal_name_ar: str = Field(min_length=1, max_length=255)
    legal_name_en: str = Field(min_length=1, max_length=255)
    trn: TrnStr
    license_no: str | None = Field(default=None, max_length=100)
    emirate: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    revenue_band: RevenueBand = RevenueBand.UNKNOWN


class TenantUpdateIn(BaseModel):
    """TRN is intentionally absent — immutable after signup (DECISIONS D-013)."""

    legal_name_ar: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name_en: str | None = Field(default=None, min_length=1, max_length=255)
    license_no: str | None = Field(default=None, max_length=100)
    emirate: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    revenue_band: RevenueBand | None = None


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name_ar: str
    legal_name_en: str
    trn: str
    license_no: str | None
    emirate: str | None
    address: str | None
    revenue_band: RevenueBand
    status: str
