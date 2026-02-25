"""Metadata endpoint exposing categories, accounts, users, and enums."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.models import Account, Category, User
from app.schemas import (
    AccountOut,
    CategoryChild,
    CategoryOut,
    MetaResponse,
    PaymentMethod,
    TransactionType,
    UserOut,
)
from app.tz import now_jakarta

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@router.get("/meta", response_model=MetaResponse)
async def get_meta(db: Session = Depends(get_db)):
    parents = (
        db.query(Category)
        .filter(Category.is_active == 1, Category.parent_id.is_(None))
        .order_by(Category.display_name)
        .all()
    )

    categories_out: list[CategoryOut] = []
    for p in parents:
        children = (
            db.query(Category)
            .filter(Category.is_active == 1, Category.parent_id == p.id)
            .order_by(Category.display_name)
            .all()
        )
        cat_out = CategoryOut(
            id=p.id,
            display_name=p.display_name,
            parent_id=None,
            is_active=bool(p.is_active),
            children=[CategoryChild.model_validate(c) for c in children],
        )
        categories_out.append(cat_out)

    accounts = db.query(Account).filter(Account.is_active == 1).order_by(Account.display_name).all()
    users = db.query(User).order_by(User.display_name).all()

    return MetaResponse(
        categories=categories_out,
        accounts=[AccountOut.model_validate(a) for a in accounts],
        users=[UserOut.model_validate(u) for u in users],
        payment_methods=[m.value for m in PaymentMethod],
        transaction_types=[t.value for t in TransactionType],
        server_time=now_jakarta(),
    )
