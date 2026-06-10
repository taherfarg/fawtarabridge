"""Shared field types with coded validation errors.

Custom error *types* raised here (``trn_invalid``, ``phone_invalid``,
``password_weak``) are mapped to bilingual catalog codes by the request
validation handler in ``app.api.errors``.
"""

import re
from typing import Annotated

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

TRN_RE = re.compile(r"^\d{15}$")
PHONE_RE = re.compile(r"^\+?\d{8,15}$")
PASSWORD_MIN_LENGTH = 8


def validate_trn(value: str) -> str:
    value = value.strip()
    if not TRN_RE.fullmatch(value):
        raise PydanticCustomError("trn_invalid", "TRN must be exactly 15 digits")
    return value


def validate_phone(value: str) -> str:
    value = value.strip().replace(" ", "")
    if not PHONE_RE.fullmatch(value):
        raise PydanticCustomError("phone_invalid", "Phone must be 8-15 digits, optional leading +")
    return value


def validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise PydanticCustomError(
            "password_weak", "Password must be at least {min_length} characters"
        )
    return value


TrnStr = Annotated[str, AfterValidator(validate_trn)]
PhoneStr = Annotated[str, AfterValidator(validate_phone)]
PasswordStr = Annotated[str, AfterValidator(validate_password)]
