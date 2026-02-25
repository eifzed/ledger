"""Transaction endpoints: create, list, get, void, correct."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.errors import LedgerHTTPException
from app.schemas import (
    TransactionCreate,
    TransactionCreateResponse,
    TransactionListResponse,
    TransactionOut,
)
from app.services import transaction_service

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.post("/transactions", response_model=TransactionCreateResponse, status_code=201)
async def create_transaction(body: TransactionCreate, db: Session = Depends(get_db)):
    result = transaction_service.create_transaction(db, body)
    return TransactionCreateResponse(
        transaction=TransactionOut.model_validate(result["transaction"]),
        balances=result["balances"],
        budget_status=result["budget_status"],
        warnings=result["warnings"],
    )


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    category_id: str | None = None,
    user_id: str | None = None,
    account_id: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = transaction_service.list_transactions(
        db,
        month=month,
        category_id=category_id,
        user_id=user_id,
        account_id=account_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return TransactionListResponse(
        transactions=[TransactionOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/transactions/{txn_id}", response_model=TransactionOut)
async def get_transaction(txn_id: str, db: Session = Depends(get_db)):
    txn = transaction_service.get_transaction(db, txn_id)
    if txn is None:
        raise LedgerHTTPException(404, "NOT_FOUND", "Transaction not found")
    return TransactionOut.model_validate(txn)


@router.post("/transactions/{txn_id}/void", response_model=TransactionOut)
async def void_transaction(txn_id: str, db: Session = Depends(get_db)):
    txn = transaction_service.void_transaction(db, txn_id)
    return TransactionOut.model_validate(txn)


@router.post("/transactions/{txn_id}/correct", response_model=TransactionCreateResponse)
async def correct_transaction(txn_id: str, body: TransactionCreate, db: Session = Depends(get_db)):
    result = transaction_service.correct_transaction(db, txn_id, body)
    return TransactionCreateResponse(
        transaction=TransactionOut.model_validate(result["transaction"]),
        balances=result["balances"],
        budget_status=result["budget_status"],
        warnings=result["warnings"],
    )
