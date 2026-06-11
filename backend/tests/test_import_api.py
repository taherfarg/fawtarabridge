"""CSV/Excel import: preview, commit, mapping templates, per-row bilingual reports."""

import io
import json

from fastapi.testclient import TestClient
from openpyxl import Workbook

from tests.conftest import auth_headers, signup_payload

MAPPING = {
    "columns": {
        "invoice_number": "Invoice No",
        "issue_date": "Date",
        "buyer_name": "Customer",
        "buyer_trn": "TRN",
        "description": "Item",
        "quantity": "Qty",
        "unit_price": "Price",
        "vat_treatment": "VAT",
        "exemption_reason": "Exemption",
    },
    "vat_value_map": {"5%": "S", "0%": "Z", "exempt": "E"},
    "date_format": "%d/%m/%Y",
}

CSV_OK = """Invoice No,Date,Customer,TRN,Item,Qty,Price,VAT,Exemption
INV-100,15/05/2026,Gulf Builders LLC,100765432100002,Steel pipes,10,"1,000.00",5%,
INV-100,15/05/2026,Gulf Builders LLC,100765432100002,Cement bags,5,20.00,5%,
INV-101,16/05/2026,Falcon Insurance,100888999600002,Brokerage fee,1,200,exempt,Article 42 exemption
"""


def _headers(client: TestClient):
    body = client.post("/api/v1/auth/signup", json=signup_payload()).json()
    return auth_headers(body["tokens"])


def _post_import(
    client: TestClient,
    headers: dict,
    *,
    endpoint: str = "preview",
    csv_text: str = CSV_OK,
    mapping: dict | None = None,
    meta_extra: dict | None = None,
    filename: str = "invoices.csv",
    raw: bytes | None = None,
):
    meta: dict = {"mapping": mapping or MAPPING}
    meta.update(meta_extra or {})
    content = raw if raw is not None else csv_text.encode("utf-8")
    return client.post(
        f"/api/v1/invoices/import/{endpoint}",
        headers=headers,
        files={"file": (filename, content, "text/csv")},
        data={"payload": json.dumps(meta)},
    )


def test_preview_groups_rows_and_validates(client: TestClient) -> None:
    headers = _headers(client)
    response = _post_import(client, headers)
    assert response.status_code == 200, response.text
    report = response.json()

    assert report["summary"] == {"rows": 3, "invoices": 2, "valid": 2, "invalid": 0, "created": 0}
    inv100 = report["invoices"][0]
    assert inv100["invoice_number"] == "INV-100"
    assert inv100["rows"] == [1, 2]
    assert inv100["valid"] is True
    assert inv100["invoice_id"] is None  # preview never persists

    # Nothing was created.
    assert client.get("/api/v1/invoices", headers=headers).json()["total"] == 0


def test_commit_creates_draft_invoices(client: TestClient) -> None:
    headers = _headers(client)
    report = _post_import(client, headers, endpoint="commit").json()
    assert report["summary"]["created"] == 2
    assert all(inv["invoice_id"] for inv in report["invoices"])

    listed = client.get("/api/v1/invoices", headers=headers).json()
    assert listed["total"] == 2
    by_number = {i["invoice_number"]: i for i in listed["items"]}
    # 10*1000 + 5*20 = 10100 net, +5% VAT = 10605.00
    assert by_number["INV-100"]["total_including_vat"] == "10605.00"
    assert by_number["INV-100"]["status"] == "DRAFT"
    # exempt invoice: no VAT
    assert by_number["INV-101"]["total_including_vat"] == "200.00"


def test_per_row_parse_errors_reported_bilingually(client: TestClient) -> None:
    headers = _headers(client)
    bad_csv = """Invoice No,Date,Customer,TRN,Item,Qty,Price,VAT,Exemption
INV-200,15/05/2026,Buyer LLC,100765432100002,Widget,abc,10,5%,
INV-201,31-12-2026,Buyer LLC,100765432100002,Widget,1,10,5%,
INV-202,15/05/2026,Buyer LLC,100765432100002,Widget,1,10,7%,
"""
    report = _post_import(client, headers, csv_text=bad_csv).json()
    assert report["summary"]["invalid"] == 3

    by_number = {inv["invoice_number"]: inv for inv in report["invoices"]}
    qty = by_number["INV-200"]["errors"][0]
    assert qty["code"] == "import.bad_decimal"
    assert "abc" in qty["message_en"]
    assert qty["message_ar"]

    assert by_number["INV-201"]["errors"][0]["code"] == "import.bad_date"
    vat = by_number["INV-202"]["errors"][0]
    assert vat["code"] == "import.vat_value_unknown"
    assert "7%" in vat["message_en"]


def test_engine_validation_errors_surface_in_report(client: TestClient) -> None:
    headers = _headers(client)
    csv_text = """Invoice No,Date,Customer,TRN,Item,Qty,Price,VAT,Exemption
INV-300,15/05/2026,Buyer LLC,123,Widget,1,10,5%,
INV-301,15/05/2026,Buyer LLC,100765432100002,Service,1,10,exempt,
"""
    report = _post_import(client, headers, csv_text=csv_text).json()
    by_number = {inv["invoice_number"]: inv for inv in report["invoices"]}
    assert [e["code"] for e in by_number["INV-300"]["errors"]] == ["invoice.buyer_trn_invalid"]
    assert [e["code"] for e in by_number["INV-301"]["errors"]] == [
        "invoice.line.exemption_reason_missing"
    ]


def test_missing_mapped_column_is_file_error(client: TestClient) -> None:
    headers = _headers(client)
    csv_text = "Invoice No,Date\nINV-1,15/05/2026\n"
    report = _post_import(client, headers, csv_text=csv_text).json()
    assert report["invoices"] == []
    codes = {e["code"] for e in report["file_errors"]}
    assert codes == {"import.column_missing"}
    missing_columns = {e["field"] for e in report["file_errors"]}
    assert "buyer_name" in missing_columns


def test_inconsistent_invoice_header_rejected(client: TestClient) -> None:
    headers = _headers(client)
    csv_text = """Invoice No,Date,Customer,TRN,Item,Qty,Price,VAT,Exemption
INV-400,15/05/2026,Buyer LLC,100765432100002,Widget,1,10,5%,
INV-400,16/05/2026,Buyer LLC,100765432100002,Gadget,1,10,5%,
"""
    report = _post_import(client, headers, csv_text=csv_text).json()
    inv = report["invoices"][0]
    assert inv["valid"] is False
    assert [e["code"] for e in inv["errors"]] == ["import.inconsistent_invoice"]
    assert inv["errors"][0]["field"] == "issue_date"


def test_row_without_invoice_number_is_orphan_issue(client: TestClient) -> None:
    headers = _headers(client)
    csv_text = """Invoice No,Date,Customer,TRN,Item,Qty,Price,VAT,Exemption
,15/05/2026,Buyer LLC,100765432100002,Widget,1,10,5%,
"""
    report = _post_import(client, headers, csv_text=csv_text).json()
    assert report["invoices"] == []
    assert report["row_issues"][0]["row"] == 1
    assert report["row_issues"][0]["errors"][0]["code"] == "import.required_value_missing"


def test_unsupported_and_empty_files(client: TestClient) -> None:
    headers = _headers(client)
    bad_ext = _post_import(client, headers, filename="invoices.pdf").json()
    assert bad_ext["file_errors"][0]["code"] == "import.file_unsupported"

    empty = _post_import(client, headers, csv_text="Invoice No,Date,Customer\n").json()
    assert empty["file_errors"][0]["code"] == "import.file_empty"


def test_commit_save_template_and_reuse_by_id(client: TestClient) -> None:
    headers = _headers(client)
    report = _post_import(
        client,
        headers,
        endpoint="commit",
        meta_extra={"save_template_name": "Tally export"},
    ).json()
    template_id = report["saved_template_id"]
    assert template_id

    templates = client.get("/api/v1/import/templates", headers=headers).json()
    assert [t["name"] for t in templates] == ["Tally export"]

    # Re-import a new file referencing only the template id.
    csv_text = CSV_OK.replace("INV-100", "INV-110").replace("INV-101", "INV-111")
    response = client.post(
        "/api/v1/invoices/import/commit",
        headers=headers,
        files={"file": ("more.csv", csv_text.encode("utf-8"), "text/csv")},
        data={"payload": json.dumps({"template_id": template_id})},
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["created"] == 2


def test_commit_existing_invoice_number_fails_that_invoice_only(client: TestClient) -> None:
    headers = _headers(client)
    assert _post_import(client, headers, endpoint="commit").json()["summary"]["created"] == 2

    # Same file again: both invoices now collide on their numbers.
    report = _post_import(client, headers, endpoint="commit").json()
    assert report["summary"]["created"] == 0
    assert all(not inv["valid"] for inv in report["invoices"])
    assert {e["code"] for inv in report["invoices"] for e in inv["errors"]} == {
        "invoice.number_exists"
    }


def test_import_duplicate_detection_warns(client: TestClient) -> None:
    headers = _headers(client)
    # Manually create an invoice matching INV-101's buyer/amount/date.
    client.post(
        "/api/v1/invoices",
        headers=headers,
        json={
            "invoice_number": "MANUAL-1",
            "issue_date": "2026-05-17",
            "buyer": {"name": "Falcon Insurance", "trn": "100888999600002"},
            "lines": [
                {
                    "description": "Brokerage fee",
                    "quantity": "1",
                    "unit_price": "200",
                    "vat_category": "E",
                    "vat_rate": "0",
                    "exemption_reason": "Exempt financial services",
                }
            ],
        },
    )
    report = _post_import(client, headers).json()
    by_number = {inv["invoice_number"]: inv for inv in report["invoices"]}
    warnings = by_number["INV-101"]["warnings"]
    assert [w["code"] for w in warnings] == ["invoice.possible_duplicate"]
    assert "MANUAL-1" in warnings[0]["message_en"]


def test_xlsx_import(client: TestClient) -> None:
    headers = _headers(client)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        ["Invoice No", "Date", "Customer", "TRN", "Item", "Qty", "Price", "VAT", "Exemption"]
    )
    sheet.append(
        [
            "INV-500",
            "15/05/2026",
            "Gulf Builders LLC",
            "100765432100002",
            "Steel",
            10,
            100,
            "5%",
            None,
        ]
    )
    buffer = io.BytesIO()
    workbook.save(buffer)

    response = client.post(
        "/api/v1/invoices/import/commit",
        headers=headers,
        files={
            "file": (
                "invoices.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"payload": json.dumps({"mapping": MAPPING})},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["summary"] == {"rows": 1, "invoices": 1, "valid": 1, "invalid": 0, "created": 1}

    listed = client.get("/api/v1/invoices", headers=headers).json()
    assert listed["items"][0]["total_including_vat"] == "1050.00"


def test_template_crud_and_duplicate_name(client: TestClient) -> None:
    headers = _headers(client)
    created = client.post(
        "/api/v1/import/templates",
        headers=headers,
        json={"name": "Zoho export", "mapping": MAPPING},
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    dup = client.post(
        "/api/v1/import/templates",
        headers=headers,
        json={"name": "Zoho export", "mapping": MAPPING},
    )
    assert dup.status_code == 409
    assert dup.json()["errors"][0]["code"] == "import.template_name_exists"

    assert (
        client.delete(f"/api/v1/import/templates/{template_id}", headers=headers).status_code == 204
    )
    assert client.get("/api/v1/import/templates", headers=headers).json() == []


def test_meta_without_mapping_or_template_422(client: TestClient) -> None:
    headers = _headers(client)
    response = client.post(
        "/api/v1/invoices/import/preview",
        headers=headers,
        files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")},
        data={"payload": json.dumps({})},
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["message_ar"]
