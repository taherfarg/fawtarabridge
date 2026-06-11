"""Every error code raised anywhere in the app must exist in BOTH locale catalogs."""

import re
from pathlib import Path

from app.api.errors import _PYDANTIC_TYPE_TO_CODE
from app.core.i18n import t
from app.intake.importer import IMPORT_ERROR_CODES
from app.pintae.v1.rules import ERROR_CODES as PINTAE_V1_ERROR_CODES
from app.services.invoice_service import SERVICE_ERROR_CODES

APP_DIR = Path(__file__).resolve().parents[1] / "app"
APP_ERROR_RE = re.compile(r"AppError\(\s*\"([a-z_][a-z0-9_.]*)\"")


def _collect_codes() -> set[str]:
    codes: set[str] = set(_PYDANTIC_TYPE_TO_CODE.values())
    codes.update(PINTAE_V1_ERROR_CODES)
    codes.update(IMPORT_ERROR_CODES)
    codes.update(SERVICE_ERROR_CODES)
    for path in APP_DIR.rglob("*.py"):
        codes.update(APP_ERROR_RE.findall(path.read_text(encoding="utf-8")))
    codes.add("validation.invalid")  # generic fallback used by the validation handler
    return codes


def test_all_error_codes_have_bilingual_messages() -> None:
    codes = _collect_codes()
    assert codes, "no error codes found — the scan is broken"
    missing = [
        f"{code} [{locale}]"
        for code in sorted(codes)
        for locale in ("en", "ar")
        if not t(f"errors.{code}.message", locale)  # unformatted template is fine here
    ]
    assert not missing, f"catalog entries missing: {missing}"


def test_arabic_messages_are_actually_arabic() -> None:
    arabic_re = re.compile(r"[؀-ۿ]")
    for code in sorted(_collect_codes()):
        message = t(f"errors.{code}.message", "ar")
        assert message and arabic_re.search(message), f"{code}: Arabic message looks wrong"
