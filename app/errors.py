"""Structured error types and exception handlers."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas import ErrorDetail


class NeedsClarificationError(Exception):
    def __init__(self, message: str, details: list[ErrorDetail]):
        self.message = message
        self.details = details
        super().__init__(message)


class LedgerHTTPException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: list[ErrorDetail] | None = None):
        self.code = code
        self.error_message = message
        self.details = details or []
        super().__init__(status_code=status_code, detail=message)


def needs_clarification_handler(_request: Request, exc: NeedsClarificationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "NEEDS_CLARIFICATION",
                "message": exc.message,
                "details": [d.model_dump(exclude_none=True) for d in exc.details],
            }
        },
    )


def ledger_http_handler(_request: Request, exc: LedgerHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.error_message,
                "details": [d.model_dump(exclude_none=True) for d in exc.details],
            }
        },
    )
