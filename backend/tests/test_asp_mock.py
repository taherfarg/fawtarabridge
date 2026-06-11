import pytest

from app.asp import ASPPermanentError, ASPTransientError
from app.asp.mock import MockASPAdapter
from app.asp.rejections import rejection_detail


@pytest.fixture()
def adapter() -> MockASPAdapter:
    return MockASPAdapter()


def test_send_is_idempotent_on_key(adapter: MockASPAdapter) -> None:
    first = adapter.send_invoice(
        b"<xml/>", idempotency_key="k1", sender_trn="1" * 15, receiver_trn="100765432100002"
    )
    second = adapter.send_invoice(
        b"<xml/>", idempotency_key="k1", sender_trn="1" * 15, receiver_trn="100765432100002"
    )
    assert first.message_id == second.message_id


def test_rejection_rules_by_receiver_suffix(adapter: MockASPAdapter) -> None:
    r99 = adapter.send_invoice(
        b"<a/>", idempotency_key="k99", sender_trn="1" * 15, receiver_trn="100765432100099"
    )
    assert adapter.get_status(r99.message_id).rejection_code == "BR-AE-02"

    r98 = adapter.send_invoice(
        b"<b/>", idempotency_key="k98", sender_trn="1" * 15, receiver_trn="100765432100098"
    )
    assert adapter.get_status(r98.message_id).rejection_code == "BR-CO-15"

    r94 = adapter.send_invoice(
        b"<c/>", idempotency_key="k94", sender_trn="1" * 15, receiver_trn="100765432100094"
    )
    assert adapter.get_status(r94.message_id).status == "processing"


def test_error_simulation(adapter: MockASPAdapter) -> None:
    with pytest.raises(ASPTransientError):
        adapter.send_invoice(
            b"<x/>", idempotency_key="k97", sender_trn="1" * 15, receiver_trn="100765432100097"
        )
    with pytest.raises(ASPPermanentError):
        adapter.send_invoice(
            b"<x/>", idempotency_key="k96", sender_trn="1" * 15, receiver_trn="100765432100096"
        )


def test_participant_endpoints(adapter: MockASPAdapter) -> None:
    registration = adapter.register_participant(trn="100123456700001", legal_name="X LLC")
    assert registration.status == "registered"
    assert registration.participant_id == "0235:100123456700001"
    assert adapter.register_participant(trn="100123456700095", legal_name="Y").status == "failed"

    assert adapter.lookup_participant("100123456700001").registered is True
    assert adapter.lookup_participant("100123456700095").registered is False


def test_rejection_mapping_known_and_unknown() -> None:
    known = rejection_detail("BR-AE-02", "raw reason")
    assert known.code == "rejection.buyer_trn_not_registered"
    assert "BR-AE-02" in known.message_en
    assert known.message_ar
    assert known.suggestion_ar

    unknown = rejection_detail("XX-42", "Something exotic happened")
    assert unknown.code == "rejection.unknown"
    assert "XX-42" in unknown.message_en
    assert "Something exotic happened" in unknown.message_en
    assert unknown.message_ar
