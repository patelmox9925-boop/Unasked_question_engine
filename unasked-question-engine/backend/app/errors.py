"""API error type and handlers producing a consistent ``{"error": {...}}`` shape."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.details = status_code, code, message, details


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e["loc"]) + ": " + e["msg"] for e in exc.errors()[:5]]
        return JSONResponse(
            _body("invalid_request", "The request was not valid.", {"fields": fields}),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            _body("internal_error", "An unexpected error occurred."), status_code=500
        )
