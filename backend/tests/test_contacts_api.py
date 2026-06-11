"""Contacts CRUD: TRN validation, per-tenant uniqueness, API-level tenant isolation."""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, signup_payload


def _signup(client: TestClient, email: str = "owner@example.com", trn: str = "100123456700001"):
    return client.post("/api/v1/auth/signup", json=signup_payload(email=email, trn=trn)).json()


def contact_payload(**overrides) -> dict:
    payload = {
        "name_en": "Gulf Builders LLC",
        "name_ar": "شركة بناة الخليج ذ.م.م",
        "trn": "100765432100002",
        "email": "accounts@gulfbuilders.example",
        "phone": "+97142223344",
        "city": "Abu Dhabi",
        "emirate": "Abu Dhabi",
    }
    payload.update(overrides)
    return payload


def test_contact_crud_roundtrip(client: TestClient) -> None:
    headers = auth_headers(_signup(client)["tokens"])

    created = client.post("/api/v1/contacts", headers=headers, json=contact_payload())
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]
    assert created.json()["trn"] == "100765432100002"

    fetched = client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name_ar"] == "شركة بناة الخليج ذ.م.م"

    updated = client.put(
        f"/api/v1/contacts/{contact_id}",
        headers=headers,
        json=contact_payload(city="Al Ain", default_vat_category="S"),
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Al Ain"
    assert updated.json()["default_vat_category"] == "S"

    listed = client.get("/api/v1/contacts", headers=headers)
    assert listed.json()["total"] == 1

    assert client.delete(f"/api/v1/contacts/{contact_id}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/contacts/{contact_id}", headers=headers).status_code == 404


def test_contact_invalid_trn_rejected_bilingually(client: TestClient) -> None:
    headers = auth_headers(_signup(client)["tokens"])
    response = client.post("/api/v1/contacts", headers=headers, json=contact_payload(trn="12345"))
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["code"] == "validation.trn_invalid"
    assert error["field"] == "trn"
    assert error["message_ar"]


def test_contact_duplicate_trn_within_tenant_rejected(client: TestClient) -> None:
    headers = auth_headers(_signup(client)["tokens"])
    assert (
        client.post("/api/v1/contacts", headers=headers, json=contact_payload()).status_code == 201
    )
    response = client.post(
        "/api/v1/contacts", headers=headers, json=contact_payload(name_en="Other Name")
    )
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "contact.trn_exists"


def test_contact_search(client: TestClient) -> None:
    headers = auth_headers(_signup(client)["tokens"])
    client.post("/api/v1/contacts", headers=headers, json=contact_payload())
    client.post(
        "/api/v1/contacts",
        headers=headers,
        json=contact_payload(name_en="Falcon Insurance", trn="100888999600002"),
    )

    by_name = client.get("/api/v1/contacts", headers=headers, params={"search": "falcon"})
    assert [c["name_en"] for c in by_name.json()["items"]] == ["Falcon Insurance"]

    by_trn = client.get("/api/v1/contacts", headers=headers, params={"search": "100765"})
    assert [c["trn"] for c in by_trn.json()["items"]] == ["100765432100002"]


def test_contacts_isolated_between_tenants(client: TestClient) -> None:
    a_headers = auth_headers(_signup(client)["tokens"])
    b_headers = auth_headers(
        _signup(client, email="owner-b@example.com", trn="100123456700002")["tokens"]
    )

    created = client.post("/api/v1/contacts", headers=a_headers, json=contact_payload())
    contact_id = created.json()["id"]

    # Tenant B sees an empty book and cannot fetch A's contact even by ID.
    assert client.get("/api/v1/contacts", headers=b_headers).json()["total"] == 0
    assert client.get(f"/api/v1/contacts/{contact_id}", headers=b_headers).status_code == 404
    # Same TRN is fine in another tenant (uniqueness is per tenant).
    assert (
        client.post("/api/v1/contacts", headers=b_headers, json=contact_payload()).status_code
        == 201
    )


def test_readonly_cannot_write_contacts(client: TestClient) -> None:
    owner = _signup(client)
    client.post(
        "/api/v1/tenants/me/members",
        headers=auth_headers(owner["tokens"]),
        json={
            "email": "ro@example.com",
            "full_name": "Read Only",
            "phone": "+971501111222",
            "password": "Secret123!",
            "role": "readonly",
        },
    )
    ro_tokens = client.post(
        "/api/v1/auth/login", json={"email": "ro@example.com", "password": "Secret123!"}
    ).json()["tokens"]

    response = client.post(
        "/api/v1/contacts", headers=auth_headers(ro_tokens), json=contact_payload()
    )
    assert response.status_code == 403
    # …but can read.
    assert client.get("/api/v1/contacts", headers=auth_headers(ro_tokens)).status_code == 200
