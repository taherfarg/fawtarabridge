"""Application error model: every user-facing failure is bilingual and coded.

Envelope (stable contract, reused by the M2 validation engine):
    {"errors": [{code, field, message_en, message_ar, suggestion_en, suggestion_ar}]}
"""

from typing import Any

from pydantic import BaseModel

from app.core.i18n import t


class ErrorDetail(BaseModel):
    code: str
    field: str | None = None
    message_en: str
    message_ar: str
    suggestion_en: str | None = None
    suggestion_ar: str | None = None


def build_error_detail(
    code: str,
    *,
    field: str | None = None,
    params: dict[str, Any] | None = None,
    fallback_message_en: str | None = None,
) -> ErrorDetail:
    """Render a coded error in both languages from the catalog.

    Catalog layout: ``errors.<code>.message`` and optional ``errors.<code>.suggestion``.
    A missing catalog entry falls back to the code itself (and is a bug — tests
    assert catalog completeness for all codes raised in the app).
    """
    p = params or {}
    return ErrorDetail(
        code=code,
        field=field,
        message_en=t(f"errors.{code}.message", "en", **p) or fallback_message_en or code,
        message_ar=t(f"errors.{code}.message", "ar", **p) or fallback_message_en or code,
        suggestion_en=t(f"errors.{code}.suggestion", "en", **p),
        suggestion_ar=t(f"errors.{code}.suggestion", "ar", **p),
    )


class AppError(Exception):
    """Coded, bilingual application error. ``code`` must exist in the catalog."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int = 400,
        field: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.field = field
        self.params = params or {}

    def detail(self) -> ErrorDetail:
        return build_error_detail(self.code, field=self.field, params=self.params)
