import enum


class Role(enum.StrEnum):
    OWNER = "owner"
    ACCOUNTANT = "accountant"
    STAFF = "staff"
    READONLY = "readonly"


class RevenueBand(enum.StrEnum):
    """Drives deadline messaging: ≥ AED 50M mandated Jan 2027, SMEs July 2027."""

    GTE_50M = "gte_50m"
    LT_50M = "lt_50m"
    UNKNOWN = "unknown"
