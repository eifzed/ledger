"""Account management and balance computation."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Account, Transaction
from app.schemas import AccountBalance


def list_accounts(db: Session, active_only: bool = True, owner_id: str | None = None) -> list[Account]:
    q = db.query(Account)
    if active_only:
        q = q.filter(Account.is_active == 1)
    if owner_id is not None:
        q = q.filter(Account.owner_id == owner_id)
    return q.order_by(Account.owner_id, Account.display_name).all()


def get_account(db: Session, account_id: str) -> Account | None:
    return db.query(Account).filter(Account.id == account_id).first()


def create_account(
    db: Session, account_id: str, display_name: str, acct_type: str,
    currency: str = "IDR", owner_id: str | None = None,
) -> Account:
    acct = Account(
        id=account_id, display_name=display_name,
        type=acct_type, currency=currency, owner_id=owner_id,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def compute_balances(db: Session, owner_id: str | None = None) -> list[AccountBalance]:
    """Compute current balance for every active account, optionally filtered by owner."""
    accounts = list_accounts(db, active_only=True, owner_id=owner_id)
    result: list[AccountBalance] = []

    for acct in accounts:
        balance = _compute_account_balance(db, acct.id)
        result.append(AccountBalance(
            account_id=acct.id, display_name=acct.display_name,
            owner_id=acct.owner_id, balance=balance,
        ))

    return result


def compute_single_balance(db: Session, account_id: str) -> int:
    acct = get_account(db, account_id)
    if acct is None:
        return 0
    return _compute_account_balance(db, account_id)


def _compute_account_balance(db: Session, account_id: str) -> int:
    posted = Transaction.status == "posted"

    credit = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            posted,
            Transaction.to_account_id == account_id,
            Transaction.transaction_type.in_(["income", "transfer", "adjustment"]),
        )
        .scalar()
    )

    debit = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            posted,
            Transaction.from_account_id == account_id,
            Transaction.transaction_type.in_(["expense", "transfer"]),
        )
        .scalar()
    )

    adj_from = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            posted,
            Transaction.from_account_id == account_id,
            Transaction.transaction_type == "adjustment",
        )
        .scalar()
    )

    return int(credit) - int(debit) - int(adj_from)
