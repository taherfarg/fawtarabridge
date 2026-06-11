"""Unit tests for the pure parsing/conversion functions of the importer."""

from datetime import date
from decimal import Decimal, InvalidOperation

import pytest

from app.intake.importer import (
    ImportFileError,
    parse_file,
    to_date,
    to_decimal,
    to_vat_category,
)
from app.pintae.canonical import VatCategory


def test_to_decimal_accepts_separators_and_native_types() -> None:
    assert to_decimal("1,000.50") == Decimal("1000.50")
    assert to_decimal(" 42 ") == Decimal("42")
    assert to_decimal(10) == Decimal("10")
    assert to_decimal(0.105) == Decimal("0.105")  # float via shortest repr
    assert to_decimal(Decimal("7.25")) == Decimal("7.25")


def test_to_decimal_rejects_garbage() -> None:
    with pytest.raises(InvalidOperation):
        to_decimal("abc")
    with pytest.raises(ValueError):
        to_decimal("   ")


def test_to_date_formats_and_passthrough() -> None:
    assert to_date("15/05/2026", "%d/%m/%Y") == date(2026, 5, 15)
    assert to_date(date(2026, 5, 15), "%Y-%m-%d") == date(2026, 5, 15)
    with pytest.raises(ValueError):
        to_date("2026-05-15", "%d/%m/%Y")


def test_to_vat_category_map_is_case_insensitive_and_trimmed() -> None:
    value_map = {"5%": VatCategory.STANDARD, "exempt": VatCategory.EXEMPT}
    assert to_vat_category(" 5% ", value_map) is VatCategory.STANDARD
    assert to_vat_category("EXEMPT", value_map) is VatCategory.EXEMPT
    # Bare category codes always work, whatever the case.
    assert to_vat_category("ae", {}) is VatCategory.REVERSE_CHARGE
    assert to_vat_category("s", {}) is VatCategory.STANDARD
    with pytest.raises(ValueError):
        to_vat_category("7%", value_map)


def test_parse_csv_skips_blank_lines_and_strips_bom() -> None:
    content = "﻿A,B\n1,2\n\n  ,  \n3,4\n".encode()
    parsed = parse_file("f.csv", content)
    assert parsed.headers == ["A", "B"]
    assert parsed.rows == [{"A": "1", "B": "2"}, {"A": "3", "B": "4"}]


def test_parse_file_rejects_unknown_extension() -> None:
    with pytest.raises(ImportFileError) as excinfo:
        parse_file("invoices.pdf", b"%PDF")
    assert excinfo.value.errors[0].code == "import.file_unsupported"


def test_parse_file_rejects_headers_only() -> None:
    with pytest.raises(ImportFileError) as excinfo:
        parse_file("f.csv", b"A,B\n")
    assert excinfo.value.errors[0].code == "import.file_empty"
