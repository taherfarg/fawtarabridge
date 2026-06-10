"""Password hashing (Argon2) and JWT issuing/verification."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.config import get_settings
from app.core.errors import AppError

_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def sha256_hex(value: str) -> str:
    """Digest for refresh tokens / OTP codes at rest (never store them raw)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_token(
    *,
    token_type: TokenType,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    ttl: timedelta,
    jti: str | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "type": token_type,
        "jti": jti or uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise AppError("auth.token_expired", status_code=401) from None
    except jwt.InvalidTokenError:
        raise AppError("auth.token_invalid", status_code=401) from None
    if payload.get("type") != expected_type:
        raise AppError("auth.token_invalid", status_code=401)
    return payload
