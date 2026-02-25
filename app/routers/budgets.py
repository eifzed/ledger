"""Budget endpoints: upsert, list, status."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.errors import LedgerHTTPException
from app.models import Category
from app.schemas import BudgetOut, BudgetPut, BudgetSnapshotOut, BudgetStatusResponse
from app.services import budget_service
from app.tz import now_jakarta

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.put("/budgets/{month}/{category_id}", response_model=BudgetOut)
async def upsert_budget(
    month: str,
    category_id: str,
    body: BudgetPut,
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise LedgerHTTPException(404, "NOT_FOUND", f"Category '{category_id}' not found")
    if cat.parent_id is not None:
        raise LedgerHTTPException(
            422, "VALIDATION_ERROR",
            f"Budgets must target a parent category. "
            f"'{category_id}' is a subcategory of '{cat.parent_id}'.",
        )

    budget = budget_service.upsert_budget(
        db,
        month=month,
        category_id=category_id,
        limit_amount=body.limit_amount,
        scope_user_id=body.scope_user_id,
    )
    return BudgetOut.model_validate(budget)


@router.get("/budgets", response_model=list[BudgetOut])
async def list_budgets(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    budgets = budget_service.list_budgets(db, month)
    return [BudgetOut.model_validate(b) for b in budgets]


@router.get("/budgets/status", response_model=BudgetStatusResponse)
async def budget_status(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    if not month:
        month = now_jakarta().strftime("%Y-%m")
    items, warnings = budget_service.compute_budget_status(db, month)
    return BudgetStatusResponse(month=month, budgets=items, warnings=warnings)


@router.get("/budgets/history", response_model=list[BudgetSnapshotOut])
async def budget_history(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    snapshots = budget_service.list_snapshots(db, month, limit=limit)
    return [BudgetSnapshotOut.model_validate(s) for s in snapshots]
