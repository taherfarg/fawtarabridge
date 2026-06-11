"""ASP/FTA rejection-code -> bilingual message mapping (FR-4.4).

Unknown codes fall back to ``rejection.unknown`` carrying the raw code+reason —
the customer always gets SOMETHING readable, and the raw values stay visible for
support. # SPEC-CHECK: seed list uses EN 16931/Peppol BR-* style codes; replace
with the contracted ASP's official code list.
"""

from app.core.errors import ErrorDetail, build_error_detail

REJECTION_CODE_TO_CATALOG: dict[str, str] = {
    "BR-AE-02": "rejection.buyer_trn_not_registered",
    "BR-AE-03": "rejection.supplier_trn_not_registered",
    "BR-CO-15": "rejection.totals_inconsistent",
    "BR-S-08": "rejection.vat_breakdown_invalid",
    "PEPPOL-DELIVERY-001": "rejection.receiver_unreachable",
    "XSD-VALIDATION": "rejection.schema_invalid",
}

# For the i18n catalog-completeness test.
REJECTION_ERROR_CODES: frozenset[str] = frozenset(
    {*REJECTION_CODE_TO_CATALOG.values(), "rejection.unknown"}
)


def rejection_detail(code: str | None, raw_reason: str | None) -> ErrorDetail:
    catalog_code = REJECTION_CODE_TO_CATALOG.get(code or "")
    if catalog_code is not None:
        return build_error_detail(catalog_code, params={"code": code or ""})
    return build_error_detail(
        "rejection.unknown",
        params={"code": code or "?", "reason": raw_reason or "-"},
    )
