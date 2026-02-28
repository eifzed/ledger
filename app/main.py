"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.database import Base, engine
from app.errors import (
    LedgerHTTPException,
    NeedsClarificationError,
    ledger_http_handler,
    needs_clarification_handler,
)
from app.routers import accounts, budgets, convert, health, meta, summary, transactions
from app.routers.dashboard import router as dashboard_router
from app.seed import seed_defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Ledger – Household Finance API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(NeedsClarificationError, needs_clarification_handler)
app.add_exception_handler(LedgerHTTPException, ledger_http_handler)


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(_request: Request, exc: ValidationError):
    details = []
    for err in exc.errors():
        loc = ".".join(str(l) for l in err["loc"])
        details.append({"field": loc, "issue": err["msg"]})
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": details,
            }
        },
    )


app.include_router(health.router)
app.include_router(meta.router)
app.include_router(transactions.router)
app.include_router(budgets.router)
app.include_router(accounts.router)
app.include_router(summary.router)
app.include_router(convert.router)
app.include_router(dashboard_router)
