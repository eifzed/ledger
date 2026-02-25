"""Monthly summary endpoint."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.schemas import MonthlySummary
from app.services import summary_service
from app.tz import now_jakarta

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.get("/summary/monthly", response_model=MonthlySummary)
async def get_monthly_summary(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
):
    if not month:
        month = now_jakarta().strftime("%Y-%m")
    return summary_service.monthly_summary(db, month)
