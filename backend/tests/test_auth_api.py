"""End-to-end auth + tenancy API tests (signup, login, refresh, roles, OTP)."""

from fastapi.testclient import TestClient

from tests.conftest import CapturingOTPProvider, auth_headers, signup_payload

# ---------------------------------------------------------------------------- signup


def test_signup_creates_tenant_and_owner(client: TestClient) -> None:
    response = client.post("/api/v1/auth/signup", json=signup_payload())
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["tenant"]["trn"] == "100123456700001"
    assert body["tenant"]["legal_name_ar"] == "شركة الاختبار التجارية ذ.م.م"
    assert body["user"]["email"] == "owner@example.com"
    assert body["user"]["phone_verified"] is False
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]

    # The issued token actually works and is scoped to the new tenant.
    me = client.get("/api/v1/tenants/me", headers=auth_headers(body["tokens"]))
    assert me.status_code == 200
    assert me.json()["id"] == body["tenant"]["id"]


def test_signup_duplicate_email_rejected_bilingually(client: TestClient) -> None:
    assert client.post("/api/v1/auth/signup", json=signup_payload()).status_code == 201
    response = client.post("/api/v1/auth/signup", json=signup_payload(trn="100123456700099"))
    assert response.status_code == 409
    error = response.json()["errors"][0]
    assert error["code"] == "auth.email_exists"
    assert error["field"] == "email"
    assert error["message_en"]
    assert error["message_ar"]


def test_signup_duplicate_trn_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/auth/signup", json=signup_payload()).status_code == 201
    response = client.post("/api/v1/auth/signup", json=signup_payload(email="other@example.com"))
    assert response.status_code == 409
    error = response.json()["errors"][0]
    assert error["code"] == "tenant.trn_exists"
    assert error["message_ar"]


def test_signup_invalid_trn_gets_coded_bilingual_error(client: TestClient) -> None:
    response = client.post("/api/v1/auth/signup", json=signup_payload(trn="12345"))
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["code"] == "validation.trn_invalid"
    assert error["field"] == "company.trn"
    assert "15" in error["message_en"]
    assert "15" in error["message_ar"]
    assert error["suggestion_ar"]


def test_signup_weak_password_rejected(client: TestClient) -> None:
    payload = signup_payload()
    payload["password"] = "short"
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["code"] == "validation.password_weak"
    assert "8" in error["message_en"]


# ---------------------------------------------------------------------------- login


def test_login_success(client: TestClient) -> None:
    client.post("/api/v1/auth/signup", json=signup_payload())
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "Secret123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tokens"]["access_token"]
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "owner"


def test_login_wrong_password_bilingual_401(client: TestClient) -> None:
    client.post("/api/v1/auth/signup", json=signup_payload())
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    error = response.json()["errors"][0]
    assert error["code"] == "auth.invalid_credentials"
    assert error["message_en"]
    assert error["message_ar"]


def test_login_unknown_email_same_error_as_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "whatever123"},
    )
    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "auth.invalid_credentials"


# ---------------------------------------------------------------------------- refresh


def test_refresh_rotates_tokens(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/signup", json=signup_payload()).json()["tokens"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # Old refresh token is single-use.
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401

    # The rotated one works.
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert again.status_code == 200


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/signup", json=signup_payload()).json()["tokens"]
    assert (
        client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 204
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


# ------------------------------------------------------------------- roles & members


def _add_member(client: TestClient, owner_tokens: dict, email: str, role: str) -> dict:
    response = client.post(
        "/api/v1/tenants/me/members",
        headers=auth_headers(owner_tokens),
        json={
            "email": email,
            "full_name": "Member",
            "phone": "+971502222222",
            "password": "Secret123!",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(client: TestClient, email: str, password: str = "Secret123!") -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["tokens"]


def test_staff_cannot_update_tenant_profile(client: TestClient) -> None:
    owner_tokens = client.post("/api/v1/auth/signup", json=signup_payload()).json()["tokens"]
    _add_member(client, owner_tokens, "staff@example.com", "staff")
    staff_tokens = _login(client, "staff@example.com")

    # Staff can read the company profile…
    assert client.get("/api/v1/tenants/me", headers=auth_headers(staff_tokens)).status_code == 200
    # …but cannot modify it.
    response = client.patch(
        "/api/v1/tenants/me",
        headers=auth_headers(staff_tokens),
        json={"legal_name_en": "Hijacked LLC"},
    )
    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "auth.forbidden"


def test_readonly_cannot_add_members_and_staff_cannot_list(client: TestClient) -> None:
    owner_tokens = client.post("/api/v1/auth/signup", json=signup_payload()).json()["tokens"]
    _add_member(client, owner_tokens, "ro@example.com", "readonly")
    ro_tokens = _login(client, "ro@example.com")

    response = client.post(
        "/api/v1/tenants/me/members",
        headers=auth_headers(ro_tokens),
        json={
            "email": "evil@example.com",
            "full_name": "Evil",
            "phone": "+971503333333",
            "password": "Secret123!",
            "role": "owner",
        },
    )
    assert response.status_code == 403

    _add_member(client, owner_tokens, "staff2@example.com", "staff")
    staff_tokens = _login(client, "staff2@example.com")
    assert (
        client.get("/api/v1/tenants/me/members", headers=auth_headers(staff_tokens)).status_code
        == 403
    )


def test_owner_updates_tenant_profile(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/signup", json=signup_payload()).json()["tokens"]
    response = client.patch(
        "/api/v1/tenants/me",
        headers=auth_headers(tokens),
        json={"emirate": "Sharjah", "revenue_band": "gte_50m"},
    )
    assert response.status_code == 200
    assert response.json()["emirate"] == "Sharjah"
    assert response.json()["revenue_band"] == "gte_50m"


def test_duplicate_member_rejected(client: TestClient) -> None:
    owner_tokens = client.post("/api/v1/auth/signup", json=signup_payload()).json()["tokens"]
    _add_member(client, owner_tokens, "staff@example.com", "staff")
    response = client.post(
        "/api/v1/tenants/me/members",
        headers=auth_headers(owner_tokens),
        json={
            "email": "staff@example.com",
            "full_name": "Member",
            "phone": "+971502222222",
            "password": "Secret123!",
            "role": "staff",
        },
    )
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "member.already_exists"


# ---------------------------------------------------------------- multi-tenant users


def test_accountant_switches_between_tenants(client: TestClient) -> None:
    a = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    b = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email="owner-b@example.com", trn="100123456700002"),
    ).json()

    # Both owners add the same accountant identity; the second add reuses it.
    _add_member(client, a["tokens"], "acc@example.com", "accountant")
    _add_member(client, b["tokens"], "acc@example.com", "accountant")

    login = client.post(
        "/api/v1/auth/login", json={"email": "acc@example.com", "password": "Secret123!"}
    ).json()
    assert len(login["memberships"]) == 2

    other_tenant = next(
        m["tenant_id"] for m in login["memberships"] if m["tenant_id"] != login["active_tenant_id"]
    )
    switched = client.post(
        "/api/v1/auth/switch-tenant",
        headers=auth_headers(login["tokens"]),
        json={"tenant_id": other_tenant},
    )
    assert switched.status_code == 200
    me = client.get("/api/v1/tenants/me", headers=auth_headers(switched.json()))
    assert me.json()["id"] == other_tenant


def test_switch_to_foreign_tenant_forbidden(client: TestClient) -> None:
    a = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    b = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email="owner-b@example.com", trn="100123456700002"),
    ).json()

    response = client.post(
        "/api/v1/auth/switch-tenant",
        headers=auth_headers(a["tokens"]),
        json={"tenant_id": b["tenant"]["id"]},
    )
    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "auth.not_member"


def test_cross_tenant_api_isolation(client: TestClient) -> None:
    """Tenant A's token never returns tenant B's data through the API."""
    a = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    b = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email="owner-b@example.com", trn="100123456700002"),
    ).json()

    me_a = client.get("/api/v1/tenants/me", headers=auth_headers(a["tokens"])).json()
    me_b = client.get("/api/v1/tenants/me", headers=auth_headers(b["tokens"])).json()
    assert me_a["id"] == a["tenant"]["id"]
    assert me_b["id"] == b["tenant"]["id"]

    members_a = client.get("/api/v1/tenants/me/members", headers=auth_headers(a["tokens"])).json()
    assert [m["user"]["email"] for m in members_a] == ["owner@example.com"]


# ------------------------------------------------------------------------------- OTP


def test_otp_verify_flow(client: TestClient, otp_outbox: CapturingOTPProvider) -> None:
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    assert len(otp_outbox.sent) == 1
    code = otp_outbox.last_code

    response = client.post(
        "/api/v1/auth/otp/verify", headers=auth_headers(body["tokens"]), json={"code": code}
    )
    assert response.status_code == 204

    me = client.get("/api/v1/users/me", headers=auth_headers(body["tokens"]))
    assert me.json()["phone_verified"] is True


def test_otp_wrong_code_then_correct(client: TestClient, otp_outbox: CapturingOTPProvider) -> None:
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    code = otp_outbox.last_code
    wrong = "000000" if code != "000000" else "111111"

    response = client.post(
        "/api/v1/auth/otp/verify", headers=auth_headers(body["tokens"]), json={"code": wrong}
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "otp.invalid"

    response = client.post(
        "/api/v1/auth/otp/verify", headers=auth_headers(body["tokens"]), json={"code": code}
    )
    assert response.status_code == 204


def test_otp_attempts_are_limited(client: TestClient, otp_outbox: CapturingOTPProvider) -> None:
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    code = otp_outbox.last_code
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/otp/verify", headers=auth_headers(body["tokens"]), json={"code": wrong}
        )
        assert response.status_code == 400

    # Even the correct code is now rejected — a new code must be requested.
    response = client.post(
        "/api/v1/auth/otp/verify", headers=auth_headers(body["tokens"]), json={"code": code}
    )
    assert response.status_code == 429
    assert response.json()["errors"][0]["code"] == "otp.too_many_attempts"

    # Fix path: request a fresh code and verify with it.
    assert (
        client.post("/api/v1/auth/otp/request", headers=auth_headers(body["tokens"]))
    ).status_code == 204
    response = client.post(
        "/api/v1/auth/otp/verify",
        headers=auth_headers(body["tokens"]),
        json={"code": otp_outbox.last_code},
    )
    assert response.status_code == 204


# -------------------------------------------------------------------- misc auth guard


def test_unauthenticated_request_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/tenants/me")
    assert response.status_code == 401
    error = response.json()["errors"][0]
    assert error["code"] == "auth.not_authenticated"
    assert error["message_ar"]
