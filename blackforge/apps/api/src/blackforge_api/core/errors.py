"""Enveloppe d'erreur unique : ``{"error": {"code", "message", "request_id", "details"?}}``.

Règles de sécurité :
* un 5xx ne renvoie jamais le texte de l'exception (journalisé côté serveur uniquement) ;
* les erreurs de validation n'« écho » jamais la valeur reçue (``input``), qui peut être un secret.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from blackforge_api.core.logging import request_id_var

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Erreur métier volontairement exposée au client."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_payload(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    body = ErrorBody(code=code, message=message, request_id=request_id_var.get(), details=details)
    return ErrorResponse(error=body).model_dump(exclude_none=True)


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        error_payload(code, message, details), status_code=status_code, headers=headers
    )


def _safe_validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    # On conserve l'emplacement et le type d'erreur, jamais la valeur fournie.
    return [
        {"loc": list(err["loc"]), "type": err["type"], "message": err["msg"]}
        for err in jsonable_encoder(exc.errors())
    ]


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message)


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    message = str(exc.detail) if exc.status_code < 500 else "Erreur interne du serveur."
    return error_response(exc.status_code, code, message, headers=dict(exc.headers or {}))


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(
        422, "validation_error", "Requête invalide.", details=_safe_validation_details(exc)
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
