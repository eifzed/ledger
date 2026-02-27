"""Monthly summary computation."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Category, Transaction, User
from app.schemas import (
    CategorySpend,
    DailyTotal,
    MonthlySummary,
    ParentCategorySpend,
    UserSpend,
)
from app.services import budget_service


def monthly_summary(db: Session, month: str, user_id: str | None = None) -> MonthlySummary:
    posted = Transaction.status == "posted"
    in_month = func.strftime("%Y-%m", Transaction.effective_at) == month

    base_filters = [posted, in_month]
    if user_id:
        base_filters.append(Transaction.user_id == user_id)

    total_expenses = int(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(*base_filters, Transaction.transaction_type == "expense")
        .scalar()
    )

    total_income = int(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(*base_filters, Transaction.transaction_type == "income")
        .scalar()
    )

    by_category_rows = (
        db.query(Transaction.category_id, func.sum(Transaction.amount).label("total"))
        .filter(*base_filters, Transaction.transaction_type == "expense", Transaction.category_id.isnot(None))
        .group_by(Transaction.category_id)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    by_category: list[CategorySpend] = []
    for row in by_category_rows:
        cat = db.query(Category).filter(Category.id == row.category_id).first()
        by_category.append(CategorySpend(
            category_id=row.category_id,
            category_name=cat.display_name if cat else row.category_id,
            total=int(row.total),
        ))

    by_parent_category = _roll_up_to_parents(db, by_category)

    by_user_rows = (
        db.query(Transaction.user_id, func.sum(Transaction.amount).label("total"))
        .filter(*base_filters, Transaction.transaction_type == "expense")
        .group_by(Transaction.user_id)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    by_user: list[UserSpend] = []
    for row in by_user_rows:
        u = db.query(User).filter(User.id == row.user_id).first()
        by_user.append(UserSpend(
            user_id=row.user_id,
            display_name=u.display_name if u else row.user_id,
            total=int(row.total),
        ))

    daily_rows = (
        db.query(
            func.strftime("%Y-%m-%d", Transaction.effective_at).label("date"),
            func.sum(Transaction.amount).label("total"),
        )
        .filter(*base_filters, Transaction.transaction_type == "expense")
        .group_by(func.strftime("%Y-%m-%d", Transaction.effective_at))
        .order_by("date")
        .all()
    )
    daily_totals = [DailyTotal(date=r.date, total=int(r.total)) for r in daily_rows]

    merchant_rows = (
        db.query(Transaction.merchant, func.sum(Transaction.amount).label("total"), func.count().label("count"))
        .filter(*base_filters, Transaction.transaction_type == "expense", Transaction.merchant.isnot(None))
        .group_by(Transaction.merchant)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(10)
        .all()
    )
    top_merchants = [
        {"merchant": r.merchant, "total": int(r.total), "count": int(r.count)}
        for r in merchant_rows
    ]

    budget_items, warnings = budget_service.compute_budget_status(db, month)

    return MonthlySummary(
        month=month,
        total_expenses=total_expenses,
        total_income=total_income,
        net=total_income - total_expenses,
        by_category=by_category,
        by_parent_category=by_parent_category,
        by_user=by_user,
        daily_totals=daily_totals,
        top_merchants=top_merchants,
        budget_status=budget_items,
        warnings=warnings,
    )


def _roll_up_to_parents(db: Session, by_category: list[CategorySpend]) -> list[ParentCategorySpend]:
    """Group child category spending into parent buckets."""
    parent_totals: dict[str, int] = defaultdict(int)
    parent_children: dict[str, list[CategorySpend]] = defaultdict(list)
    parent_names: dict[str, str] = {}

    for item in by_category:
        cat = db.query(Category).filter(Category.id == item.category_id).first()
        if cat and cat.parent_id:
            pid = cat.parent_id
            parent_cat = db.query(Category).filter(Category.id == pid).first()
            parent_names[pid] = parent_cat.display_name if parent_cat else pid
        else:
            pid = item.category_id
            parent_names[pid] = item.category_name

        parent_totals[pid] += item.total
        if cat and cat.parent_id:
            parent_children[pid].append(item)

    result = [
        ParentCategorySpend(
            category_id=pid,
            category_name=parent_names[pid],
            total=parent_totals[pid],
            children=sorted(parent_children.get(pid, []), key=lambda c: c.total, reverse=True),
        )
        for pid in parent_totals
    ]
    result.sort(key=lambda p: p.total, reverse=True)
    return result
