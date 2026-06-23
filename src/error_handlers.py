from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse


logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = _request_id(request)

    if exc.status_code >= 500:
        logger.error(
            "http_exception",
            extra={"request_id": request_id, "status_code": exc.status_code},
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id},
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = _request_id(request)
    logger.info("validation_error", extra={"request_id": request_id})

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": _safe_validation_errors(exc.errors()),
            "request_id": request_id,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception("unhandled_exception", extra={"request_id": request_id})

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _safe_validation_errors(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    safe_errors = []
    for error in errors:
        safe_errors.append(
            {
                "loc": error.get("loc", []),
                "msg": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
        )

    return safe_errors

