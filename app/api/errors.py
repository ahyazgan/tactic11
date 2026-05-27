"""Standardized error response handler.

FastAPI default HTTPException → `{"detail": "..."}`. Bu modül yapılandırılmış
bir `ErrorResponse` şemasına dönüştürür: kod + mesaj + opsiyonel details +
request_id. Client'lar `code` üzerinden parse eder; string `detail` parse
etmek yerine.

Custom code'lar HTTPException raise edilirken `detail` dict olarak verilebilir:
    raise HTTPException(status_code=404, detail={"code": "team_not_found",
                                                  "message": "..."})

Default davranış: string detail → otomatik kod (HTTP status'a göre):
- 400 → "bad_request"
- 401 → "unauthorized"
- 404 → "not_found"
- 429 → "rate_limit_exceeded"
- 500 → "internal_server_error"
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id

# HTTP status → default error code mapping
_DEFAULT_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limit_exceeded",
    500: "internal_server_error",
    503: "service_unavailable",
}


def _build_error_payload(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    # `detail` legacy alan (eski clients string okur); `error` yeni structured
    # alan (code + message + optional details + request_id). İkisi yan yana
    # geçiş için.
    payload: dict[str, Any] = {
        "detail": message,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    rid = get_request_id()
    if rid is not None:
        payload["error"]["request_id"] = rid
    return payload


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """HTTPException → ErrorResponse JSON.

    `exc.detail` dict ise `code` + `message` (+ `details`) çıkarılır; string ise
    default code HTTP status'tan türetilir, message = detail.
    """
    assert isinstance(exc, HTTPException)  # add_exception_handler ile garanti
    code: str
    message: str
    details: Any | None = None
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code", _DEFAULT_CODES.get(exc.status_code, "error")))
        message = str(detail.get("message", ""))
        details = detail.get("details")
    else:
        code = _DEFAULT_CODES.get(exc.status_code, "error")
        message = str(detail) if detail else ""

    payload = _build_error_payload(
        status_code=exc.status_code, code=code, message=message, details=details
    )
    # 429'da Retry-After'ı koru (middleware ekleyebilir; biz override etmiyoruz)
    headers = exc.headers or {}
    return JSONResponse(payload, status_code=exc.status_code, headers=dict(headers))


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """FastAPI request validation hatasını ErrorResponse şemasına çevir."""
    assert isinstance(exc, RequestValidationError)
    payload = _build_error_payload(
        status_code=422,
        code="validation_error",
        message="request validation failed",
        details=exc.errors(),
    )
    return JSONResponse(payload, status_code=422)


def register_exception_handlers(app: FastAPI) -> None:
    """`app.include_router(protected)`'den önce çağrılmalı (override order)."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
