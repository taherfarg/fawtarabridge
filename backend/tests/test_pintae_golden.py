"""Golden-file suite: the PINT-AE engine's behavioural contract (see golden/README.md)."""

import json
from pathlib import Path

import pytest

from app.pintae import CanonicalInvoice, InvoiceValidationError, get_engine
from app.pintae.v1.xsd import xsd_errors

GOLDEN = Path(__file__).parent / "golden"
INPUTS = GOLDEN / "inputs"
EXPECTED = GOLDEN / "expected"

VALID_CASES = sorted(p.stem for p in INPUTS.glob("valid_*.json"))
ERROR_CASES = sorted(p.stem for p in INPUTS.glob("err_*.json"))


def load_invoice(name: str) -> CanonicalInvoice:
    raw = (INPUTS / f"{name}.json").read_text(encoding="utf-8")
    return CanonicalInvoice.model_validate_json(raw)


def test_fixture_inventory_is_complete() -> None:
    assert len(VALID_CASES) >= 5
    assert len(ERROR_CASES) >= 5
    assert len(VALID_CASES) + len(ERROR_CASES) >= 10
    # Every input has its expected counterpart and vice versa (no orphans).
    assert {f"{n}.xml" for n in VALID_CASES} == {p.name for p in EXPECTED.glob("valid_*.xml")}
    assert {f"{n}.errors.json" for n in ERROR_CASES} == {
        p.name for p in EXPECTED.glob("err_*.errors.json")
    }


@pytest.mark.parametrize("name", VALID_CASES)
def test_valid_fixture_produces_exact_golden_xml(name: str) -> None:
    engine = get_engine("pint-ae-1.0")
    result = engine.generate(load_invoice(name))
    assert result.spec_version == "pint-ae-1.0"
    expected = (EXPECTED / f"{name}.xml").read_bytes().replace(b"\r\n", b"\n")
    assert result.xml.replace(b"\r\n", b"\n") == expected


@pytest.mark.parametrize("name", VALID_CASES)
def test_valid_fixture_xml_passes_ubl_xsd(name: str) -> None:
    engine = get_engine("pint-ae-1.0")
    xml = engine.serialize(load_invoice(name))
    assert xsd_errors(xml) == []


@pytest.mark.parametrize("name", ERROR_CASES)
def test_error_fixture_matches_golden_bilingual_errors(name: str) -> None:
    engine = get_engine("pint-ae-1.0")
    got = [e.model_dump() for e in engine.validate(load_invoice(name))]
    expected = json.loads((EXPECTED / f"{name}.errors.json").read_text(encoding="utf-8"))
    assert got == expected


@pytest.mark.parametrize("name", ERROR_CASES)
def test_error_fixture_refuses_to_generate_xml(name: str) -> None:
    engine = get_engine("pint-ae-1.0")
    with pytest.raises(InvoiceValidationError) as excinfo:
        engine.generate(load_invoice(name))
    assert excinfo.value.errors  # the exception carries the full bilingual error list
