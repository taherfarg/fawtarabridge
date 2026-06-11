"""Monthly compliance summary: status counts + penalty-risk estimate (FR-5.4)."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.services.compliance_service import compute_penalty
from tests.conftest import auth_headers, signup_payload

ACCEPT_TRN = "100765432100002"


def _headers(client: TestClient):
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    return auth_headers(body["tokens"])


def _invoice(
    client: TestClient,
    headers: dict,
    number: str,
    issue_date: str,
    *,
    qty: str = "10",
    validate: bool = False,
    send: bool = False,
) -> str:
    payload = {
        "invoice_number": number,
        "issue_date": issue_date,
        "buyer": {"name": "Gulf Builders LLC", "trn": ACCEPT_TRN},
        "lines": [
            {
                "description": "Steel",
                "quantity": qty,
                "unit_price": "100",
                "vat_category": "S",
                "vat_rate": "5",
            }
        ],
    }
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"][
        "id"
    ]
    if validate or send:
        client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers)
    if send:
        client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    return invoice_id


def test_summary_counts_and_penalty(client: TestClient) -> None:
    headers = _headers(client)
    today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"
    # Stay inside the current month even when running early in a month.
    past_due = (today - timedelta(days=10)).isoformat()
    in_month_past_due = past_due if past_due[:7] == period else today.replace(day=1).isoformat()

    # 2 accepted, 3 past-due drafts, 1 fresh draft (within grace, not past due)
    _invoice(client, headers, "ACC-1", in_month_past_due, send=True)
    _invoice(client, headers, "ACC-2", in_month_past_due, qty="5", send=True)
    for i in range(3):
        _invoice(client, headers, f"DRAFT-{i}", in_month_past_due, qty=str(i + 1))
    _invoice(client, headers, "FRESH", today.isoformat())

    summary = client.get(
        "/api/v1/compliance/summary", headers=headers, params={"period": period}
    ).json()
    assert summary["period"] == period
    assert summary["total_invoices"] == 6
    assert summary["counts"]["ACCEPTED"] == 2
    assert summary["counts"]["DRAFT"] == 4
    # 3 past-due drafts x AED 100; the fresh draft is inside the grace window.
    assert summary["unsent_past_due"] == 3
    assert summary["penalty_risk_aed"] == 300
    assert summary["penalty_cap_aed"] == 5000
    assert summary["currency"] == "AED"
    assert summary["accepted_total_aed"] == "1575.00"  # 1050 + 525


def test_summary_defaults_to_current_month_and_filters_others(client: TestClient) -> None:
    headers = _headers(client)
    today = date.today()
    _invoice(client, headers, "OLD-1", "2020-01-15")  # different period
    _invoice(client, headers, "NOW-1", today.isoformat())

    current = client.get("/api/v1/compliance/summary", headers=headers).json()
    assert current["total_invoices"] == 1

    old = client.get(
        "/api/v1/compliance/summary", headers=headers, params={"period": "2020-01"}
    ).json()
    assert old["total_invoices"] == 1
    assert old["unsent_past_due"] == 1  # ancient draft is definitely past due
    assert old["penalty_risk_aed"] == 100


def test_invalid_period_rejected_bilingually(client: TestClient) -> None:
    headers = _headers(client)
    response = client.get(
        "/api/v1/compliance/summary", headers=headers, params={"period": "2026-13"}
    )
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["code"] == "compliance.invalid_period"
    assert error["message_ar"]


def test_penalty_is_capped_at_5000_per_month() -> None:
    assert compute_penalty(0) == 0
    assert compute_penalty(3) == 300
    assert compute_penalty(50) == 5000
    assert compute_penalty(500) == 5000
