"""Mock ASP: full lifecycle without sandbox credentials (architecture rule 3).

Behavior is deterministic, keyed on the RECEIVER TRN suffix so tests and demos
can trigger every path with ordinary-looking invoices:

    …99  rejected with BR-AE-02   (buyer TRN not registered with the FTA)
    …98  rejected with BR-CO-15   (document totals inconsistent)
    …97  transient send error      (exercises retry/backoff/dead-letter)
    …96  permanent send error      (malformed-request class)
    …94  stays "processing"        (final result arrives via the signed webhook)
    else accepted immediately

# SPEC-CHECK: rejection codes follow the EN 16931/Peppol BR-* convention; replace
# with the real ASP's code list when sandbox documentation is available.
"""

import hashlib
import uuid
from typing import ClassVar

from app.asp.base import (
    ASPAdapter,
    ASPPermanentError,
    ASPTransientError,
    ParticipantInfo,
    ParticipantRegistration,
    SendResult,
    StatusResult,
)


class MockASPAdapter(ASPAdapter):
    name: ClassVar[str] = "mock"

    # Class-level stores: the mock keeps state across instances within a process
    # (worker + API in tests). reset() clears them between tests.
    _sent_keys: ClassVar[dict[str, str]] = {}  # idempotency_key -> message_id
    _statuses: ClassVar[dict[str, StatusResult]] = {}  # message_id -> result

    @classmethod
    def reset(cls) -> None:
        cls._sent_keys.clear()
        cls._statuses.clear()

    def register_participant(self, *, trn: str, legal_name: str) -> ParticipantRegistration:
        if trn.endswith("95"):
            return ParticipantRegistration(participant_id="", status="failed")
        # SPEC-CHECK: UAE Peppol participant scheme placeholder "0235".
        return ParticipantRegistration(participant_id=f"0235:{trn}", status="registered")

    def send_invoice(
        self, xml: bytes, *, idempotency_key: str, sender_trn: str, receiver_trn: str | None
    ) -> SendResult:
        receiver = receiver_trn or ""
        if receiver.endswith("97"):
            raise ASPTransientError("mock: gateway timeout (simulated)")
        if receiver.endswith("96"):
            raise ASPPermanentError("mock: request rejected by gateway (simulated 400)")

        existing = self._sent_keys.get(idempotency_key)
        if existing is not None:
            return SendResult(message_id=existing)  # idempotent re-delivery

        digest = hashlib.sha256(xml).hexdigest()[:8]
        message_id = f"mock-{digest}-{uuid.uuid4().hex[:8]}"
        self._sent_keys[idempotency_key] = message_id

        if receiver.endswith("99"):
            result = StatusResult(
                status="rejected",
                rejection_code="BR-AE-02",
                rejection_reason="Buyer TRN is not registered with the FTA",
            )
        elif receiver.endswith("98"):
            result = StatusResult(
                status="rejected",
                rejection_code="BR-CO-15",
                rejection_reason="Document level totals are inconsistent",
            )
        elif receiver.endswith("94"):
            result = StatusResult(status="processing")
        else:
            result = StatusResult(status="accepted")
        self._statuses[message_id] = result
        return SendResult(message_id=message_id)

    def get_status(self, message_id: str) -> StatusResult:
        try:
            return self._statuses[message_id]
        except KeyError:
            raise ASPPermanentError(f"mock: unknown message id {message_id}") from None

    def lookup_participant(self, trn: str) -> ParticipantInfo:
        if trn.endswith("95"):
            return ParticipantInfo(peppol_id=None, registered=False)
        return ParticipantInfo(peppol_id=f"0235:{trn}", registered=True)
