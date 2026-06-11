"""The demo seed must keep working — the dashboard demo (M6) depends on it."""

from fastapi.testclient import TestClient

from scripts.seed_demo import DEMO_EMAIL, main
from tests.conftest import auth_headers


def test_seed_creates_30_invoices_across_statuses(client: TestClient) -> None:
    main()
    main()  # idempotent second run

    tokens = client.post(
        "/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": "Demo12345!"}
    ).json()["tokens"]
    headers = auth_headers(tokens)

    listed = client.get("/api/v1/invoices", headers=headers, params={"limit": 200}).json()
    assert listed["total"] == 30
    statuses = {i["status"] for i in listed["items"]}
    assert statuses == {"ACCEPTED", "REJECTED", "SENT", "QUEUED", "ERROR", "VALIDATED", "DRAFT"}

    # Accepted invoices were archived; the dashboard summary endpoint works.
    assert client.get("/api/v1/archive", headers=headers).json()["total"] == 12
    summary = client.get("/api/v1/compliance/summary", headers=headers).json()
    assert summary["penalty_cap_aed"] == 5000

    contacts = client.get("/api/v1/contacts", headers=headers).json()
    assert contacts["total"] == 6
