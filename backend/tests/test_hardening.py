"""M8: rate limiting, production-secret guardrails, member management, readiness."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from tests.conftest import auth_headers, signup_payload


def test_auth_rate_limit_blocks_burst(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.rate_limit import _redis

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 3)
    for key in _redis().scan_iter("ratelimit:auth:*"):  # leftovers from a same-minute run
        _redis().delete(key)

    statuses = [
        client.post(
            "/api/v1/auth/login", json={"email": "x@x.com", "password": "wrongpass1"}
        ).status_code
        for _ in range(5)
    ]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429
    error = client.post(
        "/api/v1/auth/login", json={"email": "x@x.com", "password": "wrongpass1"}
    ).json()["errors"][0]
    assert error["code"] == "auth.rate_limited"
    assert error["message_ar"]


def test_production_refuses_dev_secrets() -> None:
    settings = Settings(env="prod")  # all dev defaults
    problems = settings.validate_production_secrets()
    assert "FAWTARA_JWT_SECRET" in problems
    assert "FAWTARA_ASP_WEBHOOK_SECRET" in problems

    clean = Settings(
        env="prod",
        jwt_secret="x" * 40,
        asp_webhook_secret="y" * 40,
        database_url="postgresql+psycopg://app:realpassword@db:5432/fawtara",
    )
    assert clean.validate_production_secrets() == []


def test_readiness_endpoint(client: TestClient) -> None:
    body = client.get("/health/ready").json()
    assert body == {"database": "ok", "status": "ok"}


def test_member_role_change_and_removal(client: TestClient) -> None:
    owner = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    headers = auth_headers(owner["tokens"])
    member = client.post(
        "/api/v1/tenants/me/members",
        headers=headers,
        json={
            "email": "m@example.com",
            "full_name": "M",
            "phone": "+971501111222",
            "password": "Secret123!",
            "role": "staff",
        },
    ).json()
    user_id = member["user"]["id"]

    changed = client.patch(
        f"/api/v1/tenants/me/members/{user_id}", headers=headers, json={"role": "accountant"}
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "accountant"

    assert (
        client.delete(f"/api/v1/tenants/me/members/{user_id}", headers=headers).status_code == 204
    )
    members = client.get("/api/v1/tenants/me/members", headers=headers).json()
    assert len(members) == 1  # only the owner remains


def test_last_owner_cannot_be_removed_or_demoted(client: TestClient) -> None:
    owner = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    headers = auth_headers(owner["tokens"])
    owner_id = owner["user"]["id"]

    response = client.delete(f"/api/v1/tenants/me/members/{owner_id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "member.last_owner"

    response = client.patch(
        f"/api/v1/tenants/me/members/{owner_id}", headers=headers, json={"role": "staff"}
    )
    assert response.status_code == 409
