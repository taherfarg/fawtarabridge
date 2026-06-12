"""Plan catalog (FR-8.1). Prices in AED/month; overage is AED 1 per transmitted
invoice beyond the included quota — transmissions are NEVER blocked (FR-8.2)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str
    price_aed: int
    included_invoices: int


PLANS: dict[str, Plan] = {
    "starter": Plan("starter", 149, 100),
    "growth": Plan("growth", 349, 500),
    # PRD prices the Accountant plan by client companies (<=20); the invoice
    # quota is our own working assumption until pricing is finalized (D-053).
    "accountant": Plan("accountant", 999, 2000),
}

OVERAGE_RATE_AED = 1
TRIAL_DAYS = 14
WARNING_THRESHOLD = 0.8
