"""End-to-end transmission lifecycle against the mock ASP (Celery eager mode)."""

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.asp.webhook import compute_signature
from app.config import get_settings
from app.services.transmission_service import backoff_seconds, execute_transmission
from tests.conftest import auth_headers, signup_payload

ACCEPT_TRN = "100765432100002"
REJECT_TRN = "100765432100099"
TRANSIENT_TRN = "100765432100097"
PERMANENT_TRN = "100765432100096"
PROCESSING_TRN = "100765432100094"


def _headers(client: TestClient):
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    return auth_headers(body["tokens"])


def _make_validated_invoice(
    client: TestClient, headers: dict, *, number: str = "INV-1", buyer_trn: str = ACCEPT_TRN
) -> str:
    payload = {
        "invoice_number": number,
        "issue_date": "2026-05-15",
        "buyer": {"name": "Gulf Builders LLC", "trn": buyer_trn},
        "lines": [
            {
                "description": "Steel pipes",
                "quantity": "10",
                "unit_price": "100",
                "vat_category": "S",
                "vat_rate": "5",
            }
        ],
    }
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"][
        "id"
    ]
    report = client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers).json()
    assert report["status"] == "VALIDATED", report
    return invoice_id


def _send(client: TestClient, headers: dict, invoice_id: str) -> dict:
    response = client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


# ------------------------------------------------------------------ happy path


def test_full_lifecycle_to_accepted(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers)
    sent = _send(client, headers, invoice_id)
    assert sent["invoice_status"] == "QUEUED"  # state at queue time (202)

    detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()
    assert detail["status"] == "ACCEPTED"
    assert detail["latest_transmission"]["status"] == "accepted"
    assert detail["latest_transmission"]["asp_message_id"].startswith("mock-")
    assert detail["latest_transmission"]["attempt_count"] == 1

    # Full audited chain: created -> VALIDATED -> QUEUED -> SENT -> ACCEPTED.
    audit = client.get(f"/api/v1/invoices/{invoice_id}/audit", headers=headers).json()
    chain = [
        ((e["before"] or {}).get("status"), (e["after"] or {}).get("status"))
        for e in audit
        if e["action"] == "invoice.status_changed"
    ]
    assert chain == [
        ("DRAFT", "VALIDATED"),
        ("VALIDATED", "QUEUED"),
        ("QUEUED", "SENT"),
        ("SENT", "ACCEPTED"),
    ]
    assert audit[0]["action"] == "invoice.created"
    # Transitions performed by the worker are attributed to the system.
    sent_event = next(e for e in audit if (e["after"] or {}).get("status") == "SENT")
    assert sent_event["actor_type"] == "system"


def test_send_requires_validated_status(client: TestClient) -> None:
    headers = _headers(client)
    payload = {
        "invoice_number": "INV-D",
        "issue_date": "2026-05-15",
        "buyer": {"name": "B", "trn": ACCEPT_TRN},
        "lines": [
            {
                "description": "x",
                "quantity": "1",
                "unit_price": "10",
                "vat_category": "S",
                "vat_rate": "5",
            }
        ],
    }
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"][
        "id"
    ]
    response = client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    assert response.status_code == 409
    error = response.json()["errors"][0]
    assert error["code"] == "invoice.not_sendable"
    assert "DRAFT" in error["message_en"]
    assert error["message_ar"]


def test_double_send_rejected(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers)
    _send(client, headers, invoice_id)  # ends ACCEPTED (terminal)
    response = client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "invoice.not_sendable"


# ------------------------------------------------------------ rejection + fix


def test_rejection_with_bilingual_reason_then_fix_and_resend(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers, buyer_trn=REJECT_TRN)
    _send(client, headers, invoice_id)

    detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()
    assert detail["status"] == "REJECTED"
    rejection = detail["latest_transmission"]["rejection"]
    assert rejection["code"] == "rejection.buyer_trn_not_registered"
    assert "BR-AE-02" in rejection["message_en"]
    assert rejection["message_ar"]
    assert rejection["suggestion_ar"]

    # Fix-and-resend: edit (REJECTED -> DRAFT), validate, send again -> ACCEPTED.
    fixed = {
        "invoice_number": "INV-1",
        "issue_date": "2026-05-15",
        "buyer": {"name": "Gulf Builders LLC", "trn": ACCEPT_TRN},
        "lines": [
            {
                "description": "Steel pipes",
                "quantity": "10",
                "unit_price": "100",
                "vat_category": "S",
                "vat_rate": "5",
            }
        ],
    }
    updated = client.put(f"/api/v1/invoices/{invoice_id}", headers=headers, json=fixed).json()
    assert updated["invoice"]["status"] == "DRAFT"
    assert (
        client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers).json()["status"]
        == "VALIDATED"
    )
    _send(client, headers, invoice_id)
    final = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()
    assert final["status"] == "ACCEPTED"

    # Two transmissions on record, newest first.
    transmissions = client.get(
        f"/api/v1/invoices/{invoice_id}/transmissions", headers=headers
    ).json()
    assert [t["status"] for t in transmissions] == ["accepted", "rejected"]


def test_direct_resend_after_rejection(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers, buyer_trn=REJECT_TRN)
    _send(client, headers, invoice_id)
    assert (
        client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()["status"] == "REJECTED"
    )

    response = client.post(f"/api/v1/invoices/{invoice_id}/resend", headers=headers)
    assert response.status_code == 202
    # Content unchanged -> mock rejects again; flow holds and keys stay unique.
    assert (
        client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()["status"] == "REJECTED"
    )


def test_resend_requires_rejected_or_error(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers)
    response = client.post(f"/api/v1/invoices/{invoice_id}/resend", headers=headers)
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "invoice.not_resendable"


# ------------------------------------------------- retries, dead letter, errors


def _queue_only(client: TestClient, headers: dict, invoice_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Queue without dispatching (so retry behavior can be driven manually)."""
    from unittest.mock import patch

    with patch("app.api.routes.invoices.transmit_invoice") as task:
        client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
        (t_id, tenant_id), _ = task.delay.call_args
    return uuid.UUID(t_id), uuid.UUID(tenant_id)


def test_transient_errors_retry_then_dead_letter(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers, buyer_trn=TRANSIENT_TRN)
    transmission_id, tenant_id = _queue_only(client, headers, invoice_id)

    max_attempts = get_settings().transmission_max_attempts
    for expected_attempt in range(1, max_attempts):
        assert execute_transmission(transmission_id, tenant_id) == ("retry", expected_attempt)
    # The final attempt dead-letters and flips the invoice to ERROR.
    assert execute_transmission(transmission_id, tenant_id) == ("done", max_attempts)

    detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()
    assert detail["status"] == "ERROR"
    assert detail["latest_transmission"]["status"] == "dead_letter"
    assert detail["latest_transmission"]["attempt_count"] == max_attempts

    # Admin visibility: it shows up in the dead-letter queue.
    dead = client.get("/api/v1/transmissions/dead-letter", headers=headers).json()
    assert [d["status"] for d in dead] == ["dead_letter"]

    # Re-executing a finalized transmission is a no-op (at-least-once delivery).
    assert execute_transmission(transmission_id, tenant_id)[0] == "done"


def test_permanent_error_fails_without_retry(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers, buyer_trn=PERMANENT_TRN)
    transmission_id, tenant_id = _queue_only(client, headers, invoice_id)

    assert execute_transmission(transmission_id, tenant_id) == ("done", 1)
    detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()
    assert detail["status"] == "ERROR"
    assert detail["latest_transmission"]["status"] == "failed"
    assert "simulated 400" in detail["latest_transmission"]["last_error"]


def test_backoff_is_exponential_and_capped() -> None:
    base = get_settings().transmission_backoff_base_seconds
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [base, base * 2, base * 4, base * 8]
    assert backoff_seconds(50) == 1800


# ------------------------------------------------------------------- webhooks


def _webhook(client: TestClient, payload: dict, *, secret: str | None = None) -> object:
    body = json.dumps(payload).encode()
    signature = compute_signature(secret or get_settings().asp_webhook_secret, body)
    return client.post(
        "/api/v1/webhooks/asp/mock",
        content=body,
        headers={"X-ASP-Signature": signature, "Content-Type": "application/json"},
    )


def test_async_clearance_via_signed_webhook(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers, buyer_trn=PROCESSING_TRN)
    _send(client, headers, invoice_id)

    # Mock left it processing: invoice parked at SENT awaiting the callback.
    detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()
    assert detail["status"] == "SENT"
    transmissions = client.get(
        f"/api/v1/invoices/{invoice_id}/transmissions", headers=headers
    ).json()
    assert transmissions[0]["status"] == "sent"

    response = _webhook(
        client,
        {
            "idempotency_key": _transmission_key(transmissions[0]["id"]),
            "status": "accepted",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"result": "applied"}
    assert (
        client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()["status"] == "ACCEPTED"
    )

    # Duplicate callback is acknowledged but ignored.
    response = _webhook(
        client,
        {"idempotency_key": _transmission_key(transmissions[0]["id"]), "status": "accepted"},
    )
    assert response.json() == {"result": "ignored"}


def _transmission_key(transmission_id: str) -> str:
    """Read the idempotency key directly (admin engine — test-only backdoor)."""
    from sqlalchemy import create_engine

    from tests.conftest import ADMIN_TEST_URL

    engine = create_engine(ADMIN_TEST_URL)
    with engine.connect() as conn:
        key = conn.execute(
            text("SELECT idempotency_key FROM transmissions WHERE id = :id"),
            {"id": transmission_id},
        ).scalar_one()
    engine.dispose()
    return key


def test_webhook_bad_signature_rejected(client: TestClient) -> None:
    response = _webhook(client, {"idempotency_key": "x", "status": "accepted"}, secret="wrong")
    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "webhook.invalid_signature"


def test_webhook_unknown_key_404(client: TestClient) -> None:
    fake = f"{uuid.uuid4()}:{uuid.uuid4()}:abcd:1"
    response = _webhook(client, {"idempotency_key": fake, "status": "accepted"})
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "webhook.unknown_message"


# ------------------------------------------------------------- audit & guards


def test_audit_log_is_append_only_at_db_level(client: TestClient, db_session) -> None:
    import pytest
    from sqlalchemy.exc import ProgrammingError

    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers)
    assert invoice_id  # produced audit events

    # The app role physically lacks UPDATE/DELETE on audit_events.
    with pytest.raises(ProgrammingError, match="permission denied"):
        db_session.execute(text("UPDATE audit_events SET action = 'tampered'"))
    db_session.rollback()
    with pytest.raises(ProgrammingError, match="permission denied"):
        db_session.execute(text("DELETE FROM audit_events"))
    db_session.rollback()


def test_readonly_cannot_send(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _make_validated_invoice(client, headers)
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
    ro_tokens = client.post(
        "/api/v1/auth/login", json={"email": "ro@example.com", "password": "Secret123!"}
    ).json()["tokens"]
    response = client.post(f"/api/v1/invoices/{invoice_id}/send", headers=auth_headers(ro_tokens))
    assert response.status_code == 403


# ------------------------------------------------------------- ASP onboarding


def test_asp_onboarding_flow(client: TestClient) -> None:
    headers = _headers(client)
    me = client.get("/api/v1/tenants/me", headers=headers).json()
    assert me["asp_onboarding_status"] == "not_started"

    response = client.post("/api/v1/tenants/me/onboard-asp", headers=headers)
    assert response.status_code == 202

    me = client.get("/api/v1/tenants/me", headers=headers).json()
    assert me["asp_onboarding_status"] == "registered"  # eager worker ran inline
    assert me["asp_participant_id"] == "0235:100123456700001"

    # Second attempt is refused.
    response = client.post("/api/v1/tenants/me/onboard-asp", headers=headers)
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "tenant.asp_already_registered"
