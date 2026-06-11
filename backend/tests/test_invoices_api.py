"""Manual invoice API: create/list/detail/edit, validate flow, XML, duplicates."""

from fastapi.testclient import TestClient
from lxml import etree

from tests.conftest import auth_headers, signup_payload


def _headers(client: TestClient, email: str = "owner@example.com", trn: str = "100123456700001"):
    body = client.post("/api/v1/auth/signup", json=signup_payload(email=email, trn=trn)).json()
    return auth_headers(body["tokens"])


def invoice_payload(number: str = "INV-1", **overrides) -> dict:
    payload = {
        "invoice_number": number,
        "issue_date": "2026-05-15",
        "buyer": {"name": "Gulf Builders LLC", "trn": "100765432100002"},
        "lines": [
            {
                "description": "Steel pipes 2-inch",
                "quantity": "10",
                "unit_price": "100",
                "vat_category": "S",
                "vat_rate": "5",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_create_valid_invoice_as_draft(client: TestClient) -> None:
    headers = _headers(client)
    response = client.post("/api/v1/invoices", headers=headers, json=invoice_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["errors"] == []
    assert body["warnings"] == []
    assert body["invoice"]["status"] == "DRAFT"
    assert body["invoice"]["total_including_vat"] == "1050.00"
    assert body["invoice"]["buyer_trn"] == "100765432100002"


def test_create_invalid_invoice_saves_draft_with_errors(client: TestClient) -> None:
    headers = _headers(client)
    payload = invoice_payload()
    payload["buyer"] = {"name": "Walk-in", "trn": "123"}  # bad TRN
    response = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["invoice"]["status"] == "DRAFT"
    codes = [e["code"] for e in body["errors"]]
    assert codes == ["invoice.buyer_trn_invalid"]
    assert body["errors"][0]["message_ar"]


def test_supplier_always_comes_from_tenant_profile(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=invoice_payload()).json()[
        "invoice"
    ]["id"]
    detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=headers).json()
    # From signup_payload's company block — not from anything the caller sent.
    assert detail["canonical"]["supplier"]["trn"] == "100123456700001"
    assert detail["canonical"]["supplier"]["name"] == "Test Trading LLC"
    assert detail["canonical"]["supplier"]["name_ar"] == "شركة الاختبار التجارية ذ.م.م"


def test_duplicate_invoice_number_409(client: TestClient) -> None:
    headers = _headers(client)
    assert (
        client.post("/api/v1/invoices", headers=headers, json=invoice_payload()).status_code == 201
    )
    response = client.post(
        "/api/v1/invoices",
        headers=headers,
        json=invoice_payload(issue_date="2026-06-01"),
    )
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "invoice.number_exists"


def test_duplicate_detection_flags_same_buyer_amount_nearby_date(client: TestClient) -> None:
    headers = _headers(client)
    client.post("/api/v1/invoices", headers=headers, json=invoice_payload("INV-1"))

    # Same buyer, same total, 2 days later -> warning.
    response = client.post(
        "/api/v1/invoices",
        headers=headers,
        json=invoice_payload("INV-2", issue_date="2026-05-17"),
    )
    body = response.json()
    assert body["invoice"]["duplicate_warning"] is True
    assert [w["code"] for w in body["warnings"]] == ["invoice.possible_duplicate"]
    assert "INV-1" in body["warnings"][0]["message_en"]
    assert body["warnings"][0]["message_ar"]

    # 8+ days after both INV-1 and INV-2 -> outside the ±3-day window, no warning.
    response = client.post(
        "/api/v1/invoices",
        headers=headers,
        json=invoice_payload("INV-3", issue_date="2026-05-25"),
    )
    assert response.json()["invoice"]["duplicate_warning"] is False

    # Same window but different amount -> no warning.
    payload = invoice_payload("INV-4", issue_date="2026-05-16")
    payload["lines"][0]["quantity"] = "9"
    assert (
        client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"][
            "duplicate_warning"
        ]
        is False
    )


def test_validate_flow_and_edit_resets_to_draft(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=invoice_payload()).json()[
        "invoice"
    ]["id"]

    validated = client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers).json()
    assert validated["errors"] == []
    assert validated["status"] == "VALIDATED"
    assert validated["spec_version"] == "pint-ae-1.0"

    # Editing re-opens the draft and clears the pinned spec version.
    updated = client.put(
        f"/api/v1/invoices/{invoice_id}",
        headers=headers,
        json=invoice_payload(note="updated"),
    ).json()
    assert updated["invoice"]["status"] == "DRAFT"
    assert updated["invoice"]["spec_version"] is None


def test_validate_invalid_invoice_reports_errors(client: TestClient) -> None:
    headers = _headers(client)
    payload = invoice_payload()
    payload["lines"][0]["vat_rate"] = "12"
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"][
        "id"
    ]

    report = client.post(f"/api/v1/invoices/{invoice_id}/validate", headers=headers).json()
    assert report["status"] == "DRAFT"
    assert [e["code"] for e in report["errors"]] == ["invoice.line.vat_rate_mismatch"]


def test_xml_download_for_valid_invoice(client: TestClient) -> None:
    headers = _headers(client)
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=invoice_payload()).json()[
        "invoice"
    ]["id"]
    response = client.get(f"/api/v1/invoices/{invoice_id}/xml", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    tree = etree.fromstring(response.content)
    ns = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
    assert tree.xpath("cbc:ID/text()", namespaces=ns) == ["INV-1"]


def test_xml_refused_for_invalid_invoice(client: TestClient) -> None:
    headers = _headers(client)
    payload = invoice_payload()
    payload["buyer"] = {"name": "X", "trn": "bad"}
    invoice_id = client.post("/api/v1/invoices", headers=headers, json=payload).json()["invoice"][
        "id"
    ]

    response = client.get(f"/api/v1/invoices/{invoice_id}/xml", headers=headers)
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "invoice.buyer_trn_invalid"


def test_list_filters(client: TestClient) -> None:
    headers = _headers(client)
    client.post("/api/v1/invoices", headers=headers, json=invoice_payload("INV-1"))
    client.post(
        "/api/v1/invoices",
        headers=headers,
        json=invoice_payload("INV-2", issue_date="2026-06-20"),
    )
    other_buyer = invoice_payload("INV-3", issue_date="2026-06-20")
    other_buyer["buyer"] = {"name": "Falcon Insurance", "trn": "100888999600002"}
    client.post("/api/v1/invoices", headers=headers, json=other_buyer)

    by_date = client.get(
        "/api/v1/invoices", headers=headers, params={"from": "2026-06-01", "to": "2026-06-30"}
    ).json()
    assert {i["invoice_number"] for i in by_date["items"]} == {"INV-2", "INV-3"}

    by_buyer = client.get("/api/v1/invoices", headers=headers, params={"buyer": "falcon"}).json()
    assert [i["invoice_number"] for i in by_buyer["items"]] == ["INV-3"]

    by_status = client.get("/api/v1/invoices", headers=headers, params={"status": "DRAFT"}).json()
    assert by_status["total"] == 3


def test_invoice_with_buyer_contact(client: TestClient) -> None:
    headers = _headers(client)
    contact = client.post(
        "/api/v1/contacts",
        headers=headers,
        json={
            "name_en": "Gulf Builders LLC",
            "name_ar": "بناة الخليج",
            "trn": "100765432100002",
            "city": "Abu Dhabi",
            "emirate": "Abu Dhabi",
        },
    ).json()

    payload = invoice_payload()
    payload.pop("buyer")
    payload["buyer_contact_id"] = contact["id"]
    response = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["errors"] == []
    assert body["invoice"]["buyer_trn"] == "100765432100002"
    assert body["invoice"]["buyer_contact_id"] == contact["id"]

    detail = client.get(f"/api/v1/invoices/{body['invoice']['id']}", headers=headers).json()
    assert detail["canonical"]["buyer"]["name_ar"] == "بناة الخليج"
    assert detail["canonical"]["buyer"]["address"]["emirate"] == "Abu Dhabi"


def test_invoices_isolated_between_tenants_via_api(client: TestClient) -> None:
    a_headers = _headers(client)
    b_headers = _headers(client, email="owner-b@example.com", trn="100123456700002")

    invoice_id = client.post("/api/v1/invoices", headers=a_headers, json=invoice_payload()).json()[
        "invoice"
    ]["id"]
    assert client.get("/api/v1/invoices", headers=b_headers).json()["total"] == 0
    assert client.get(f"/api/v1/invoices/{invoice_id}", headers=b_headers).status_code == 404


def test_missing_buyer_and_contact_rejected(client: TestClient) -> None:
    headers = _headers(client)
    payload = invoice_payload()
    payload.pop("buyer")
    response = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert response.status_code == 422
