"""Transaction creation, querying, voiding, and correction."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.errors import LedgerHTTPException
from app.models import Account, Category, Transaction, User
from app.schemas import ErrorDetail, TransactionCreate, TransactionType
from app.services import account_service, budget_service
from app.services.budget_service import get_category_family
from app.tz import now_jakarta


def create_transaction(db: Session, data: TransactionCreate) -> dict:
    _validate_references(db, data)

    effective = data.effective_at or now_jakarta()
    month = effective.strftime("%Y-%m")

    txn = Transaction(
        id=str(uuid.uuid4()),
        effective_at=effective,
        user_id=data.user_id,
        transaction_type=data.transaction_type.value,
        amount=data.amount,
        currency=data.currency,
        category_id=data.category_id,
        description=data.description,
        merchant=data.merchant,
        payment_method=data.payment_method.value if data.payment_method else None,
        from_account_id=data.from_account_id,
        to_account_id=data.to_account_id,
        note=data.note,
        status="posted",
        metadata_json=json.dumps(data.metadata) if data.metadata else None,
    )

    db.add(txn)
    db.commit()
    db.refresh(txn)

    balances = account_service.compute_balances(db)

    category_ids = [data.category_id] if data.category_id else []
    budget_items, warnings = budget_service.compute_budget_status_for_categories(db, month, category_ids)

    return {
        "transaction": txn,
        "balances": balances,
        "budget_status": budget_items,
        "warnings": warnings,
    }


def list_transactions(
    db: Session,
    *,
    month: str | None = None,
    category_id: str | None = None,
    user_id: str | None = None,
    account_id: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    q = db.query(Transaction).filter(Transaction.status == "posted")

    if month:
        q = q.filter(func.strftime("%Y-%m", Transaction.effective_at) == month)
    if category_id:
        family = get_category_family(db, category_id)
        q = q.filter(Transaction.category_id.in_(family))
    if user_id:
        q = q.filter(Transaction.user_id == user_id)
    if account_id:
        q = q.filter(
            (Transaction.from_account_id == account_id)
            | (Transaction.to_account_id == account_id)
        )
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            Transaction.description.ilike(pattern)
            | Transaction.merchant.ilike(pattern)
            | Transaction.note.ilike(pattern)
        )

    total = q.count()
    rows = q.order_by(Transaction.effective_at.desc()).limit(limit).offset(offset).all()
    return rows, total


def get_transaction(db: Session, txn_id: str) -> Transaction | None:
    return db.query(Transaction).filter(Transaction.id == txn_id).first()


def void_transaction(db: Session, txn_id: str) -> Transaction:
    txn = get_transaction(db, txn_id)
    if txn is None:
        raise LedgerHTTPException(404, "NOT_FOUND", "Transaction not found")
    if txn.status == "voided":
        raise LedgerHTTPException(400, "ALREADY_VOIDED", "Transaction is already voided")
    txn.status = "voided"
    db.commit()
    db.refresh(txn)
    return txn


def correct_transaction(db: Session, txn_id: str, data: TransactionCreate) -> dict:
    original = get_transaction(db, txn_id)
    if original is None:
        raise LedgerHTTPException(404, "NOT_FOUND", "Original transaction not found")

    original.status = "voided"
    db.flush()

    _validate_references(db, data)
    effective = data.effective_at or now_jakarta()

    new_txn = Transaction(
        id=str(uuid.uuid4()),
        effective_at=effective,
        user_id=data.user_id,
        transaction_type=data.transaction_type.value,
        amount=data.amount,
        currency=data.currency,
        category_id=data.category_id,
        description=data.description,
        merchant=data.merchant,
        payment_method=data.payment_method.value if data.payment_method else None,
        from_account_id=data.from_account_id,
        to_account_id=data.to_account_id,
        note=data.note,
        status="posted",
        correction_of=txn_id,
        metadata_json=json.dumps(data.metadata) if data.metadata else None,
    )
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)

    month = effective.strftime("%Y-%m")
    balances = account_service.compute_balances(db)
    category_ids = [data.category_id] if data.category_id else []
    budget_items, warnings = budget_service.compute_budget_status_for_categories(db, month, category_ids)

    return {
        "transaction": new_txn,
        "balances": balances,
        "budget_status": budget_items,
        "warnings": warnings,
    }


def _validate_references(db: Session, data: TransactionCreate) -> None:
    missing: list[ErrorDetail] = []

    if not db.query(User).filter(User.id == data.user_id).first():
        missing.append(ErrorDetail(field="user_id", issue=f"User '{data.user_id}' not found"))

    if data.category_id and not db.query(Category).filter(Category.id == data.category_id).first():
        missing.append(ErrorDetail(field="category_id", issue=f"Category '{data.category_id}' not found"))

    if data.from_account_id and not db.query(Account).filter(Account.id == data.from_account_id).first():
        missing.append(ErrorDetail(field="from_account_id", issue=f"Account '{data.from_account_id}' not found"))

    if data.to_account_id and not db.query(Account).filter(Account.id == data.to_account_id).first():
        missing.append(ErrorDetail(field="to_account_id", issue=f"Account '{data.to_account_id}' not found"))

    if missing:
        raise LedgerHTTPException(422, "VALIDATION_ERROR", "Referenced entities not found", missing)
