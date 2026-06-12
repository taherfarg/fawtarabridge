"""Bulk validate/send: per-invoice results, failures never poison the batch."""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, signup_payload

ACCEPT_TRN = "100765432100002"


def _headers(client: TestClient):
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    return auth_headers(body["tokens"])


def _draft(client: TestClient, headers: dict, number: str, *, trn: str = ACCEPT_TRN) -> str:
    payload = {
        "invoice_number": number,
        "issue_date": "2026-05-15",
        "buyer": {"name": "Gulf Builders LLC", "trn": trn},
        "lines": [
            {
                "description": "Steel",
                "quantity": "1",
                "unit_price": "100",
                "vat_category": "S",
                "vat_rate": "5",
            }
        ],
    }
    return client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"]["id"]


def test_bulk_validate_mixed_results(client: TestClient) -> None:
    headers = _headers(client)
    good = _draft(client, headers, "B-1")
    bad = _draft(client, headers, "B-2", trn="123")  # invalid buyer TRN

    response = client.post(
        "/api/v1/invoices/bulk", headers=headers, json={"action": "validate", "ids": [good, bad]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_id = {r["id"]: r for r in body["results"]}
    assert by_id[good]["status"] == "VALIDATED"
    assert by_id[bad]["ok"] is False
    assert by_id[bad]["errors"][0]["code"] == "invoice.buyer_trn_invalid"
    assert by_id[bad]["errors"][0]["message_ar"]


def test_bulk_send_skips_unsendable_and_sends_rest(client: TestClient) -> None:
    headers = _headers(client)
    ready = _draft(client, headers, "B-3")
    client.post(f"/api/v1/invoices/{ready}/validate", headers=headers)
    still_draft = _draft(client, headers, "B-4")

    response = client.post(
        "/api/v1/invoices/bulk",
        headers=headers,
        json={"action": "send", "ids": [ready, still_draft]},
    )
    body = response.json()
    assert body["succeeded"] == 1
    by_id = {r["id"]: r for r in body["results"]}
    assert by_id[still_draft]["errors"][0]["code"] == "invoice.not_sendable"

    # The sendable one went through the whole eager pipeline to ACCEPTED.
    detail = client.get(f"/api/v1/invoices/{ready}", headers=headers).json()
    assert detail["status"] == "ACCEPTED"


def test_bulk_requires_write_role(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _draft(client, headers, "B-5")
    client.post(
        "/api/v1/tenants/me/members",
        headers=headers,
        json={
            "email": "ro@example.com",
            "full_name": "RO",
            "phone": "+971501111222",
            "password": "Secret123!",
            "role": "readonly",
        },
    )
    ro = client.post(
        "/api/v1/auth/login", json={"email": "ro@example.com", "password": "Secret123!"}
    ).json()["tokens"]
    response = client.post(
        "/api/v1/invoices/bulk",
        headers=auth_headers(ro),
        json={"action": "validate", "ids": [invoice_id]},
    )
    assert response.status_code == 403
