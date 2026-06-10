import uuid
from datetime import timedelta

import pytest

from app.core.errors import AppError
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    sha256_hex,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("Secret123!")
    assert hashed != "Secret123!"
    assert verify_password("Secret123!", hashed)
    assert not verify_password("wrong-password", hashed)


def test_sha256_hex_is_deterministic() -> None:
    assert sha256_hex("abc") == sha256_hex("abc")
    assert sha256_hex("abc") != sha256_hex("abd")


def test_jwt_roundtrip() -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    token = create_token(
        token_type="access",
        user_id=user_id,
        tenant_id=tenant_id,
        role="owner",
        ttl=timedelta(minutes=5),
    )
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == str(user_id)
    assert payload["tid"] == str(tenant_id)
    assert payload["role"] == "owner"


def test_expired_token_rejected() -> None:
    token = create_token(
        token_type="access",
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="owner",
        ttl=timedelta(seconds=-1),
    )
    with pytest.raises(AppError) as excinfo:
        decode_token(token, expected_type="access")
    assert excinfo.value.code == "auth.token_expired"


def test_wrong_token_type_rejected() -> None:
    token = create_token(
        token_type="refresh",
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="owner",
        ttl=timedelta(minutes=5),
    )
    with pytest.raises(AppError) as excinfo:
        decode_token(token, expected_type="access")
    assert excinfo.value.code == "auth.token_invalid"


def test_garbage_token_rejected() -> None:
    with pytest.raises(AppError) as excinfo:
        decode_token("not-a-jwt", expected_type="access")
    assert excinfo.value.code == "auth.token_invalid"
