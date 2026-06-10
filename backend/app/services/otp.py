"""OTP delivery interface. Real WhatsApp OTP arrives later; the contract is fixed now.

The provider only *delivers* codes — generation, storage (hashed) and verification
live in the auth service, so swapping providers never touches auth logic.
"""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class OTPProvider(Protocol):
    def send(self, phone: str, code: str) -> None: ...


class ConsoleOTPProvider:
    """Dev/test stub: logs the code instead of sending it."""

    def send(self, phone: str, code: str) -> None:
        logger.info("OTP for %s: %s", phone, code)


def get_otp_provider() -> OTPProvider:
    """FastAPI dependency — overridden in tests, replaced by WhatsApp BSP later."""
    return ConsoleOTPProvider()
