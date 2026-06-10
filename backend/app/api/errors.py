"""Exception handlers: every failure leaves the API as a bilingual error envelope."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError, ErrorDetail, build_error_detail
from app.core.i18n import t

logger = logging.getLogger(__name__)

# pydantic error type -> catalog code (codes without an entry fall through to generic)
_PYDANTIC_TYPE_TO_CODE = {
    "trn_invalid": "validation.trn_invalid",
    "phone_invalid": "validation.phone_invalid",
    "password_weak": "validation.password_weak",
    "missing": "validation.missing",
}


def _field_from_loc(loc: tuple[str | int, ...]) -> str | None:
    parts = [str(p) for p in loc if p != "body"]
    return ".".join(parts) or None


def map_request_validation_error(exc: RequestValidationError) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []
    for err in exc.errors():
        field = _field_from_loc(tuple(err.get("loc", ())))
        code = _PYDANTIC_TYPE_TO_CODE.get(err["type"])
        if code is not None:
            params = {"min_length": 8} if err["type"] == "password_weak" else {}
            details.append(build_error_detail(code, field=field, params=params))
        else:
            details.append(
                ErrorDetail(
                    code="validation.invalid",
                    field=field,
                    message_en=err.get("msg", "Invalid value"),
                    message_ar=t("errors.validation.invalid.message", "ar")
                    or "قيمة غير صالحة لهذا الحقل",
                )
            )
    return details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"errors": [exc.detail().model_dump()]},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = map_request_validation_error(exc)
        return JSONResponse(
            status_code=422,
            content={"errors": [d.model_dump() for d in details]},
        )
