"""ASP adapter contract (architecture rule 3). One implementation per provider;
the rest of the system depends only on this module. Designed for N providers —
the real ASP (Flick / ClearTax / …) becomes a sibling of MockASPAdapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Literal


class ASPError(Exception):
    """Base for adapter failures."""


class ASPTransientError(ASPError):
    """Retryable: timeouts, 5xx, rate limits. The send task backs off and retries."""


class ASPPermanentError(ASPError):
    """Not retryable: malformed request, auth failure. Goes straight to admin."""


@dataclass(frozen=True)
class ParticipantRegistration:
    participant_id: str
    status: Literal["pending", "registered", "failed"]


@dataclass(frozen=True)
class ParticipantInfo:
    peppol_id: str | None
    registered: bool


@dataclass(frozen=True)
class SendResult:
    """The ASP accepted the document for processing (corner 2 -> corner 3)."""

    message_id: str


@dataclass(frozen=True)
class StatusResult:
    status: Literal["processing", "accepted", "rejected", "error"]
    rejection_code: str | None = None
    rejection_reason: str | None = None


class ASPAdapter(ABC):
    name: ClassVar[str]

    @abstractmethod
    def register_participant(self, *, trn: str, legal_name: str) -> ParticipantRegistration:
        """Onboard the tenant as a Peppol participant via this ASP."""

    @abstractmethod
    def send_invoice(
        self, xml: bytes, *, idempotency_key: str, sender_trn: str, receiver_trn: str | None
    ) -> SendResult:
        """Submit a PINT-AE document. MUST be idempotent on idempotency_key."""

    @abstractmethod
    def get_status(self, message_id: str) -> StatusResult:
        """Clearance status for a previously sent document."""

    @abstractmethod
    def lookup_participant(self, trn: str) -> ParticipantInfo:
        """Peppol directory lookup (FR-2.3)."""
