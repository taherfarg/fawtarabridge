"""Archive (FR-7): immutable records on clearance, search, downloads, ZIP export."""

import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.services.archive_service import retention_until
from tests.conftest import auth_headers, signup_payload

ACCEPT_TRN = "100765432100002"
REJECT_TRN = "100765432100099"


def _headers(client: TestClient, email: str = "owner@example.com", trn: str = "100123456700001"):
    body = client.post("/api/v1/auth/signup", json=signup_payload(email=email, trn=trn)).json()
    return auth_headers(body["tokens"])


def _accepted_invoice(
    client: TestClient,
    headers: dict,
    *,
    number: str = "INV-1",
    buyer_trn: str = ACCEPT_TRN,
    issue_date: str = "2026-05-15",
) -> str:
    payload = {
        "invoice_number": number,
        "issue_date": issue_date,
        "buyer": {"name": "Gulf Builders LLC", "trn": buyer_trn},
        "lines": [
            {
                "description": "Steel pipes",
                "description_ar": "أنابيب فولاذية",
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
    client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers)
    client.post(f"/api/v1/invoices/{invoice_id}/send", headers=headers)
    return invoice_id


def test_clearance_creates_immutable_archive_record(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = _accepted_invoice(client, headers)

    listed = client.get("/api/v1/archive", headers=headers).json()
    assert listed["total"] == 1
    record = listed["items"][0]
    assert record["invoice_id"] == invoice_id
    assert record["invoice_number"] == "INV-1"
    assert record["retention_until"] == "2031-05-15"  # issue + 5 years
    assert record["ack"]["status"] == "accepted"
    assert record["ack"]["message_id"].startswith("mock-")
    assert record["spec_version"] == "pint-ae-1.0"

    # Archived XML byte-identical to the engine's output for this invoice.
    archived_xml = client.get(f"/api/v1/archive/{record['id']}/xml", headers=headers).content
    live_xml = client.get(f"/api/v1/invoices/{invoice_id}/xml", headers=headers).content
    assert archived_xml == live_xml

    # PDF is real and readable.
    pdf_bytes = client.get(f"/api/v1/archive/{record['id']}/pdf", headers=headers).content
    assert pdf_bytes.startswith(b"%PDF")
    pdf_text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
    assert "INV-1" in pdf_text
    assert "1050.00" in pdf_text
    assert "TAX INVOICE" in pdf_text


def test_rejected_invoice_is_not_archived(client: TestClient) -> None:
    headers = _headers(client)
    _accepted_invoice(client, headers, buyer_trn=REJECT_TRN)
    assert client.get("/api/v1/archive", headers=headers).json()["total"] == 0


def test_archive_is_append_only_at_db_level(client: TestClient, db_session) -> None:
    headers = _headers(client)
    _accepted_invoice(client, headers)
    with pytest.raises(ProgrammingError, match="permission denied"):
        db_session.execute(text("UPDATE archive_records SET invoice_number = 'tampered'"))
    db_session.rollback()
    with pytest.raises(ProgrammingError, match="permission denied"):
        db_session.execute(text("DELETE FROM archive_records"))
    db_session.rollback()


def test_archive_search_filters(client: TestClient) -> None:
    headers = _headers(client)
    _accepted_invoice(client, headers, number="INV-A", issue_date="2026-03-10")
    _accepted_invoice(client, headers, number="INV-B", issue_date="2026-05-20")

    by_number = client.get("/api/v1/archive", headers=headers, params={"search": "INV-A"}).json()
    assert [r["invoice_number"] for r in by_number["items"]] == ["INV-A"]

    by_buyer = client.get("/api/v1/archive", headers=headers, params={"search": "gulf"}).json()
    assert by_buyer["total"] == 2

    by_date = client.get(
        "/api/v1/archive", headers=headers, params={"from": "2026-05-01", "to": "2026-05-31"}
    ).json()
    assert [r["invoice_number"] for r in by_date["items"]] == ["INV-B"]


def test_archive_isolated_between_tenants(client: TestClient) -> None:
    a_headers = _headers(client)
    b_headers = _headers(client, email="b@example.com", trn="100123456700002")
    _accepted_invoice(client, a_headers)

    assert client.get("/api/v1/archive", headers=b_headers).json()["total"] == 0
    record_id = client.get("/api/v1/archive", headers=a_headers).json()["items"][0]["id"]
    assert client.get(f"/api/v1/archive/{record_id}/xml", headers=b_headers).status_code == 404


def test_zip_export_contains_xml_pdf_and_index(client: TestClient) -> None:
    headers = _headers(client)
    _accepted_invoice(client, headers, number="INV-A", issue_date="2026-05-10")
    _accepted_invoice(client, headers, number="INV-B", issue_date="2026-06-05")

    response = client.get("/api/v1/archive/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    bundle = zipfile.ZipFile(io.BytesIO(response.content))
    assert set(bundle.namelist()) == {
        "INV-A.xml",
        "INV-A.pdf",
        "INV-B.xml",
        "INV-B.pdf",
        "index.csv",
    }
    index = bundle.read("index.csv").decode("utf-8")
    assert "INV-A,2026-05-10,Gulf Builders LLC" in index
    assert "retention_until" in index.splitlines()[0]

    # Date-filtered export only contains the matching invoice.
    filtered = client.get("/api/v1/archive/export", headers=headers, params={"from": "2026-06-01"})
    assert set(zipfile.ZipFile(io.BytesIO(filtered.content)).namelist()) == {
        "INV-B.xml",
        "INV-B.pdf",
        "index.csv",
    }


def test_zip_export_requires_admin_role(client: TestClient) -> None:
    headers = _headers(client)
    client.post(
        "/api/v1/tenants/me/members",
        headers=headers,
        json={
            "email": "staff@example.com",
            "full_name": "Staff",
            "phone": "+971501111222",
            "password": "Secret123!",
            "role": "staff",
        },
    )
    staff_tokens = client.post(
        "/api/v1/auth/login", json={"email": "staff@example.com", "password": "Secret123!"}
    ).json()["tokens"]
    assert (
        client.get("/api/v1/archive/export", headers=auth_headers(staff_tokens)).status_code == 403
    )


def test_draft_pdf_is_watermarked_copy(client: TestClient) -> None:
    headers = _headers(client)
    payload = {
        "invoice_number": "DRAFT-1",
        "issue_date": "2026-05-15",
        "buyer": {"name": "Gulf Builders LLC", "trn": ACCEPT_TRN},
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
    pdf_bytes = client.get(f"/api/v1/invoices/{invoice_id}/pdf", headers=headers).content
    text_content = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
    assert "COPY" in text_content
    assert "DRAFT" in text_content


def test_retention_until_handles_leap_day() -> None:
    assert retention_until(date(2026, 5, 15)) == date(2031, 5, 15)
    assert retention_until(date(2024, 2, 29)) == date(2029, 2, 28)
