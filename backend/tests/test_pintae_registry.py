"""Spec versioning: engines are isolated, additive, and selectable per version."""

import pytest

from app.core.errors import ErrorDetail
from app.pintae import (
    CanonicalInvoice,
    InvoiceEngine,
    UnknownSpecVersionError,
    available_spec_versions,
    get_engine,
    register_engine,
)
from app.pintae.registry import _engines
from app.pintae.v1 import PintAeV1Engine
from tests.pintae_builders import make_invoice


def test_default_engine_is_v1() -> None:
    engine = get_engine()
    assert engine.spec_version == "pint-ae-1.0"
    assert isinstance(engine, PintAeV1Engine)
    assert get_engine("pint-ae-1.0") is engine


def test_unknown_version_raises() -> None:
    with pytest.raises(UnknownSpecVersionError):
        get_engine("pint-ae-99.0")


def test_duplicate_registration_rejected() -> None:
    with pytest.raises(ValueError, match="already registered"):
        register_engine(PintAeV1Engine())


class FakeV2Engine(InvoiceEngine):
    spec_version = "pint-ae-test-2.0"

    def validate(self, invoice: CanonicalInvoice) -> list[ErrorDetail]:
        return []

    def serialize(self, invoice: CanonicalInvoice) -> bytes:
        return b"<fake/>"


def test_second_version_registers_without_touching_v1() -> None:
    v1_before = get_engine("pint-ae-1.0")
    register_engine(FakeV2Engine())
    try:
        assert get_engine("pint-ae-test-2.0").generate(make_invoice()).xml == b"<fake/>"
        assert "pint-ae-test-2.0" in available_spec_versions()
        # v1 is exactly the same object and still serializes real UBL.
        assert get_engine("pint-ae-1.0") is v1_before
        assert get_engine("pint-ae-1.0").generate(make_invoice()).xml.startswith(b"<?xml")
    finally:
        _engines.pop("pint-ae-test-2.0", None)


def test_generated_xml_records_spec_version() -> None:
    result = get_engine().generate(make_invoice())
    assert result.spec_version == "pint-ae-1.0"
