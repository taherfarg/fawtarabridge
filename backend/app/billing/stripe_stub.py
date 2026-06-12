"""Payment provider contract + console stub. Real Stripe lands later; nothing
outside this module may import stripe-anything (architecture: clean interface)."""

import logging
import uuid
from typing import Protocol

logger = logging.getLogger(__name__)


class PaymentProvider(Protocol):
    def start_subscription(self, *, tenant_id: uuid.UUID, plan: str) -> str:
        """Returns the provider-side subscription id."""
        ...

    def report_overage(self, *, tenant_id: uuid.UUID, period: str, count: int) -> None: ...


class ConsolePaymentProvider:
    def start_subscription(self, *, tenant_id: uuid.UUID, plan: str) -> str:
        logger.info("stripe-stub: subscription %s -> plan %s", tenant_id, plan)
        return f"sub_stub_{uuid.uuid4().hex[:10]}"

    def report_overage(self, *, tenant_id: uuid.UUID, period: str, count: int) -> None:
        logger.info("stripe-stub: overage %s %s = %s invoices", tenant_id, period, count)


def get_payment_provider() -> PaymentProvider:
    return ConsolePaymentProvider()
