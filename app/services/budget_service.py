"""Budget management, status computation, and change history."""

from __future__ import annotations

import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Budget, BudgetSnapshot, Category, Transaction
from app.schemas import BudgetStatusItem, BudgetWarningSeverity, WarningItem


def get_category_family(db: Session, category_id: str) -> list[str]:
    """Return [category_id] + all child IDs for a parent category.

    If category_id is itself a child (has parent_id), returns just [category_id].
    """
    children = (
        db.query(Category.id)
        .filter(Category.parent_id == category_id)
        .all()
    )
    return [category_id] + [c.id for c in children]


def resolve_parent_category(db: Session, category_id: str) -> str | None:
    """Given a category_id (child or parent), return the parent category ID.

    If category_id is already a parent, returns itself.
    If category_id is a child, returns its parent_id.
    Returns None if category not found.
    """
    cat = db.query(Category).filter(Category.id == category_id).first()
    if cat is None:
        return None
    return cat.parent_id if cat.parent_id else cat.id


def upsert_budget(
    db: Session,
    month: str,
    category_id: str,
    limit_amount: int,
    scope_user_id: str | None = None,
    source: str = "api",
) -> Budget:
    existing = (
        db.query(Budget)
        .filter(
            Budget.month == month,
            Budget.category_id == category_id,
            Budget.scope_user_id == scope_user_id if scope_user_id else Budget.scope_user_id.is_(None),
        )
        .first()
    )

    previous_amount = existing.limit_amount if existing else None

    if existing:
        existing.limit_amount = limit_amount
        db.flush()
        budget = existing
    else:
        budget = Budget(
            month=month,
            category_id=category_id,
            limit_amount=limit_amount,
            scope_user_id=scope_user_id,
        )
        db.add(budget)
        db.flush()

    _record_snapshot(db, month, category_id, previous_amount, limit_amount, source)

    db.commit()
    db.refresh(budget)
    return budget


def bulk_upsert_budgets(
    db: Session,
    month: str,
    changes: dict[str, int],
    source: str = "dashboard",
) -> list[Budget]:
    """Upsert multiple budgets at once (from dashboard form).

    Records a single snapshot per changed category.
    """
    results: list[Budget] = []
    for category_id, limit_amount in changes.items():
        existing = (
            db.query(Budget)
            .filter(
                Budget.month == month,
                Budget.category_id == category_id,
                Budget.scope_user_id.is_(None),
            )
            .first()
        )

        previous_amount = existing.limit_amount if existing else None

        if previous_amount == limit_amount:
            if existing:
                results.append(existing)
            continue

        if existing:
            existing.limit_amount = limit_amount
            db.flush()
            results.append(existing)
        else:
            budget = Budget(
                month=month,
                category_id=category_id,
                limit_amount=limit_amount,
            )
            db.add(budget)
            db.flush()
            results.append(budget)

        _record_snapshot(db, month, category_id, previous_amount, limit_amount, source)

    db.commit()
    return results


def list_budgets(db: Session, month: str) -> list[Budget]:
    return (
        db.query(Budget)
        .filter(Budget.month == month)
        .order_by(Budget.category_id)
        .all()
    )


def compute_budget_status(db: Session, month: str) -> tuple[list[BudgetStatusItem], list[WarningItem]]:
    budgets = list_budgets(db, month)
    items: list[BudgetStatusItem] = []
    warnings: list[WarningItem] = []

    for b in budgets:
        family_ids = get_category_family(db, b.category_id)
        used = _category_family_spend(db, month, family_ids, b.scope_user_id)
        remaining = b.limit_amount - used
        percent = used / b.limit_amount if b.limit_amount > 0 else 0.0

        cat = db.query(Category).filter(Category.id == b.category_id).first()
        cat_name = cat.display_name if cat else b.category_id

        warning_text: str | None = None
        severity: BudgetWarningSeverity | None = None

        if percent >= 1.0:
            warning_text = f"{cat_name} has EXCEEDED budget ({percent:.0%})"
            severity = BudgetWarningSeverity.error
        elif percent >= 0.8:
            warning_text = f"{cat_name} is at {percent:.0%} of budget"
            severity = BudgetWarningSeverity.warn

        if warning_text and severity:
            warnings.append(WarningItem(type="budget", severity=severity, message=warning_text))

        items.append(BudgetStatusItem(
            category_id=b.category_id,
            category_name=cat_name,
            month=month,
            limit=b.limit_amount,
            used=used,
            remaining=remaining,
            percent=round(percent, 4),
            warning=warning_text,
            severity=severity,
        ))

    return items, warnings


def compute_budget_status_for_categories(
    db: Session, month: str, category_ids: list[str],
) -> tuple[list[BudgetStatusItem], list[WarningItem]]:
    """Compute budget status for categories relevant to a transaction.

    Resolves child categories to their parents to find matching budgets.
    """
    parent_ids: set[str] = set()
    for cid in category_ids:
        pid = resolve_parent_category(db, cid)
        if pid:
            parent_ids.add(pid)

    all_items, all_warnings = compute_budget_status(db, month)
    items = [i for i in all_items if i.category_id in parent_ids]
    warns = [w for w in all_warnings if any(pid in w.message for pid in parent_ids)]
    if not items and not warns:
        return all_items, all_warnings
    return items, warns


def list_snapshots(db: Session, month: str, limit: int = 50) -> list[BudgetSnapshot]:
    return (
        db.query(BudgetSnapshot)
        .filter(BudgetSnapshot.month == month)
        .order_by(BudgetSnapshot.created_at.desc())
        .limit(limit)
        .all()
    )


def _record_snapshot(
    db: Session,
    month: str,
    changed_category_id: str,
    previous_amount: int | None,
    new_amount: int,
    source: str,
) -> None:
    """Record the full budget state for a month after a change."""
    all_budgets = (
        db.query(Budget)
        .filter(Budget.month == month)
        .order_by(Budget.category_id)
        .all()
    )
    snapshot_data = {
        b.category_id: {
            "limit_amount": b.limit_amount,
            "scope_user_id": b.scope_user_id,
        }
        for b in all_budgets
    }

    snap = BudgetSnapshot(
        month=month,
        changed_category_id=changed_category_id,
        previous_amount=previous_amount,
        new_amount=new_amount,
        snapshot_json=json.dumps(snapshot_data, ensure_ascii=False),
        source=source,
    )
    db.add(snap)


def _category_family_spend(
    db: Session, month: str, category_ids: list[str], scope_user_id: str | None,
) -> int:
    """Sum expenses across a set of category IDs (parent + all children)."""
    q = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.transaction_type == "expense",
            Transaction.status == "posted",
            func.strftime("%Y-%m", Transaction.effective_at) == month,
            Transaction.category_id.in_(category_ids),
        )
    )
    if scope_user_id:
        q = q.filter(Transaction.user_id == scope_user_id)
    return int(q.scalar())
