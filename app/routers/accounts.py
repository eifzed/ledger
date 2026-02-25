"""Account endpoints: create, list, balances, adjust."""

import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.errors import LedgerHTTPException
from app.models import Account, Transaction, User
from app.schemas import AccountBalance, AccountCreate, AccountOut, AdjustRequest
from app.services import account_service
from app.tz import now_jakarta

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreate, db: Session = Depends(get_db)):
    existing = account_service.get_account(db, body.id)
    if existing:
        raise LedgerHTTPException(409, "DUPLICATE", f"Account '{body.id}' already exists")
    acct = account_service.create_account(db, body.id, body.display_name, body.type.value, body.currency)
    return AccountOut.model_validate(acct)


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(db: Session = Depends(get_db)):
    accounts = account_service.list_accounts(db)
    return [AccountOut.model_validate(a) for a in accounts]


@router.get("/accounts/balances", response_model=list[AccountBalance])
async def account_balances(db: Session = Depends(get_db)):
    return account_service.compute_balances(db)


@router.post("/accounts/{account_id}/adjust", response_model=AccountBalance)
async def adjust_account(account_id: str, body: AdjustRequest, db: Session = Depends(get_db)):
    acct = account_service.get_account(db, account_id)
    if not acct:
        raise LedgerHTTPException(404, "NOT_FOUND", f"Account '{account_id}' not found")

    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise LedgerHTTPException(422, "VALIDATION_ERROR", f"User '{body.user_id}' not found")

    txn = Transaction(
        id=str(uuid.uuid4()),
        effective_at=now_jakarta(),
        user_id=body.user_id,
        transaction_type="adjustment",
        amount=abs(body.amount),
        currency=acct.currency,
        description=f"Balance adjustment for {acct.display_name}",
        to_account_id=account_id if body.amount >= 0 else None,
        from_account_id=account_id if body.amount < 0 else None,
        note=body.note,
        status="posted",
    )
    db.add(txn)
    db.commit()

    balance = account_service.compute_single_balance(db, account_id)
    return AccountBalance(account_id=account_id, display_name=acct.display_name, balance=balance)
