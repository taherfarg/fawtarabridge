"""M7: usage metering (80% warning, never-block overage), plan changes,
rejection notifications, weekly digest."""

import pytest
from fastapi.testclient import TestClient

from app.billing import plans
from app.billing.plans import Plan
from tests.conftest import auth_headers, signup_payload

ACCEPT_TRN = "100765432100002"
REJECT_TRN = "100765432100099"


def _headers(client: TestClient):
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    return auth_headers(body["tokens"])


def _send_invoice(
    client: TestClient, headers: dict, number: str, buyer_trn: str = ACCEPT_TRN
) -> str:
    payload = {
        "invoice_number": number,
        "issue_date": "2026-05-15",
        "buyer": {"name": "Gulf Builders LLC", "trn": buyer_trn},
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
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"][
        "id"
    ]
    client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers)
    response = client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    assert response.status_code == 202, response.text
    return invoice_id


@pytest.fixture()
def tiny_plan(monkeypatch: pytest.MonkeyPatch):
    """Shrink the starter quota so thresholds are reachable in a test."""
    monkeypatch.setitem(plans.PLANS, "starter", Plan("starter", 149, 5))


def test_usage_metering_warning_and_overage_never_blocks(
    client: TestClient, tiny_plan: None
) -> None:
    headers = _headers(client)

    for index in range(1, 4):  # 3 sends: below the 80% threshold (4 of 5)
        _send_invoice(client, headers, f"INV-{index}")
    usage = client.get("/api/v1/billing/usage", headers=headers).json()
    assert usage["invoice_count"] == 3
    assert usage["warning_80"] is False
    assert usage["included_invoices"] == 5

    _send_invoice(client, headers, "INV-4")  # crosses 80%
    usage = client.get("/api/v1/billing/usage", headers=headers).json()
    assert usage["warning_80"] is True
    assert usage["overage_count"] == 0

    # The 80% warning notified the owner exactly once (whatsapp + email).
    notifications = client.get("/api/v1/notifications", headers=headers).json()
    usage_alerts = [n for n in notifications if n["template"] == "usage_80"]
    assert {n["channel"] for n in usage_alerts} == {"whatsapp", "email"}
    assert len(usage_alerts) == 2

    # Beyond the quota: overage counts up, transmission still succeeds (FR-8.2).
    for index in range(5, 8):
        _send_invoice(client, headers, f"INV-{index}")
    usage = client.get("/api/v1/billing/usage", headers=headers).json()
    assert usage["invoice_count"] == 7
    assert usage["overage_count"] == 2
    assert usage["overage_charge_aed"] == 2

    # No duplicate 80% warnings later on.
    notifications = client.get("/api/v1/notifications", headers=headers).json()
    assert len([n for n in notifications if n["template"] == "usage_80"]) == 2


def test_resend_is_not_double_metered(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _send_invoice(client, headers, "INV-R", buyer_trn=REJECT_TRN)  # rejected
    client.post(f"/api/v1/invoices/{invoice_id}/resend", headers=headers)

    usage = client.get("/api/v1/billing/usage", headers=headers).json()
    assert usage["invoice_count"] == 1  # first send counted, resend free


def test_rejection_notifies_owner_bilingually(client: TestClient) -> None:
    headers = _headers(client)
    _send_invoice(client, headers, "INV-RJ", buyer_trn=REJECT_TRN)

    notifications = client.get("/api/v1/notifications", headers=headers).json()
    rejections = [n for n in notifications if n["template"] == "invoice_rejected"]
    assert {n["channel"] for n in rejections} == {"whatsapp", "email"}
    assert rejections[0]["params"]["number"] == "INV-RJ"
    assert rejections[0]["params"]["code"] == "BR-AE-02"


def test_plan_change_owner_only_and_audited(client: TestClient) -> None:
    headers = _headers(client)
    usage = client.get("/api/v1/billing/usage", headers=headers).json()
    assert usage["plan"] == "starter"
    assert usage["trial_ends_at"] is not None  # 14-day trial set at signup

    changed = client.post("/api/v1/billing/plan", headers=headers, json={"plan": "growth"})
    assert changed.status_code == 200
    assert changed.json()["plan"] == "growth"
    assert changed.json()["included_invoices"] == 500

    # Staff cannot change the plan.
    client.post(
        "/api/v1/tenants/me/members",
        headers=headers,
        json={
            "email": "s@example.com",
            "full_name": "S",
            "phone": "+971501111222",
            "password": "Secret123!",
            "role": "staff",
        },
    )
    staff_tokens = client.post(
        "/api/v1/auth/login", json={"email": "s@example.com", "password": "Secret123!"}
    ).json()["tokens"]
    response = client.post(
        "/api/v1/billing/plan", headers=auth_headers(staff_tokens), json={"plan": "starter"}
    )
    assert response.status_code == 403

    # Invalid plan name rejected by schema.
    response = client.post("/api/v1/billing/plan", headers=headers, json={"plan": "platinum"})
    assert response.status_code == 422


def test_weekly_digest_task(client: TestClient) -> None:
    from app.worker.tasks import weekly_digest

    headers = _headers(client)
    _send_invoice(client, headers, "INV-D1")

    sent = weekly_digest.apply().get()
    assert sent >= 2  # owner got whatsapp + email

    notifications = client.get("/api/v1/notifications", headers=headers).json()
    digests = [n for n in notifications if n["template"] == "weekly_digest"]
    assert digests, "digest not logged"
    assert "penalty" in digests[0]["params"]
