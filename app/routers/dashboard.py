"""Server-rendered dashboard pages with cookie-based session auth."""

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, TimestampSigner
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Account, Category, User
from app.services import account_service, budget_service, summary_service
from app.services import transaction_service
from app.tz import now_jakarta

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(include_in_schema=False)

_signer = TimestampSigner(settings.secret_key)
_COOKIE_NAME = "ledger_session"
_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _idr(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    s = f"{abs(amount):,}".replace(",", ".")
    return f"{sign}Rp{s}"


def _get_session_user(request: Request) -> str | None:
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        return None
    try:
        username = _signer.unsign(token, max_age=_MAX_AGE).decode()
        return username
    except (BadSignature, Exception):
        return None


def _require_login(request: Request) -> str | RedirectResponse:
    user = _get_session_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return user


def _common_ctx(db: Session) -> dict:
    parents = (
        db.query(Category)
        .filter(Category.is_active == 1, Category.parent_id.is_(None))
        .order_by(Category.display_name)
        .all()
    )
    category_tree = []
    for p in parents:
        children = (
            db.query(Category)
            .filter(Category.is_active == 1, Category.parent_id == p.id)
            .order_by(Category.display_name)
            .all()
        )
        category_tree.append({"parent": p, "children": children})

    all_categories = db.query(Category).filter(Category.is_active == 1).order_by(Category.display_name).all()
    cat_name_map = {c.id: c.display_name for c in all_categories}

    return {
        "category_tree": category_tree,
        "categories": all_categories,
        "cat_name_map": cat_name_map,
        "accounts": db.query(Account).filter(Account.is_active == 1).order_by(Account.display_name).all(),
        "users": db.query(User).order_by(User.display_name).all(),
        "idr": _idr,
        "now": now_jakarta(),
    }


# ── Auth routes ───────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    if _get_session_user(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == settings.dash_user and password == settings.dash_pass:
        token = _signer.sign(username.encode()).decode()
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            _COOKIE_NAME, token,
            max_age=_MAX_AGE, httponly=True, samesite="lax",
        )
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid username or password",
    })


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(_COOKIE_NAME)
    return response


# ── Dashboard pages (all require login) ──────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def overview(request: Request, db: Session = Depends(get_db)):
    auth = _require_login(request)
    if isinstance(auth, RedirectResponse):
        return auth

    month = now_jakarta().strftime("%Y-%m")
    summary = summary_service.monthly_summary(db, month)
    all_balances = account_service.compute_balances(db)

    db_users = db.query(User).order_by(User.display_name).all()
    per_user = []
    for u in db_users:
        user_summary = summary_service.monthly_summary(db, month, user_id=u.id)
        user_balances = [b for b in all_balances if b.owner_id == u.id]
        user_total = sum(b.balance for b in user_balances)
        per_user.append({
            "user": u,
            "summary": user_summary,
            "balances": user_balances,
            "total_balance": user_total,
        })

    return templates.TemplateResponse("overview.html", {
        "request": request,
        **_common_ctx(db),
        "month": month,
        "summary": summary,
        "balances": all_balances,
        "per_user": per_user,
    })


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    month: str | None = Query(None),
    category_id: str | None = None,
    user_id: str | None = None,
    account_id: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    auth = _require_login(request)
    if isinstance(auth, RedirectResponse):
        return auth

    if not month:
        month = now_jakarta().strftime("%Y-%m")
    per_page = 30
    offset = (page - 1) * per_page

    rows, total = transaction_service.list_transactions(
        db, month=month, category_id=category_id, user_id=user_id,
        account_id=account_id, search=search, limit=per_page, offset=offset,
    )
    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse("transactions.html", {
        "request": request,
        **_common_ctx(db),
        "txns": rows,
        "month": month,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filter_category": category_id or "",
        "filter_user": user_id or "",
        "filter_account": account_id or "",
        "filter_search": search or "",
    })


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(
    request: Request,
    month: str | None = Query(None),
    db: Session = Depends(get_db),
):
    auth = _require_login(request)
    if isinstance(auth, RedirectResponse):
        return auth

    if not month:
        month = now_jakarta().strftime("%Y-%m")
    items, warnings = budget_service.compute_budget_status(db, month)
    raw_budgets = budget_service.list_budgets(db, month)
    budget_limit_map = {b.category_id: b.limit_amount for b in raw_budgets}

    parent_categories = (
        db.query(Category)
        .filter(Category.is_active == 1, Category.parent_id.is_(None))
        .order_by(Category.display_name)
        .all()
    )

    history = budget_service.list_snapshots(db, month, limit=20)

    return templates.TemplateResponse("budgets.html", {
        "request": request,
        **_common_ctx(db),
        "month": month,
        "budget_items": items,
        "raw_budgets": raw_budgets,
        "budget_limit_map": budget_limit_map,
        "parent_categories": parent_categories,
        "warnings": warnings,
        "history": history,
    })


@router.post("/budgets", response_class=HTMLResponse)
async def budgets_save(
    request: Request,
    db: Session = Depends(get_db),
):
    auth = _require_login(request)
    if isinstance(auth, RedirectResponse):
        return auth

    form = await request.form()
    month = form.get("month", now_jakarta().strftime("%Y-%m"))

    parent_categories = (
        db.query(Category)
        .filter(Category.is_active == 1, Category.parent_id.is_(None))
        .order_by(Category.display_name)
        .all()
    )

    changes: dict[str, int] = {}
    for cat in parent_categories:
        field_name = f"limit_{cat.id}"
        raw = form.get(field_name, "").strip()
        if raw:
            try:
                amount = int(raw)
                if amount > 0:
                    changes[cat.id] = amount
            except ValueError:
                pass

    if changes:
        budget_service.bulk_upsert_budgets(db, month, changes, source="dashboard")

    return RedirectResponse(url=f"/budgets?month={month}", status_code=302)


@router.get("/accounts", response_class=HTMLResponse)
async def accounts_page(request: Request, db: Session = Depends(get_db)):
    auth = _require_login(request)
    if isinstance(auth, RedirectResponse):
        return auth

    accts = account_service.list_accounts(db)
    balances = account_service.compute_balances(db)
    balance_map = {b.account_id: b.balance for b in balances}

    db_users = db.query(User).order_by(User.display_name).all()
    per_user_accounts = []
    for u in db_users:
        user_accts = [a for a in accts if a.owner_id == u.id]
        user_total = sum(balance_map.get(a.id, 0) for a in user_accts)
        per_user_accounts.append({
            "user": u,
            "accounts": user_accts,
            "total": user_total,
        })

    shared_accts = [a for a in accts if a.owner_id is None]
    shared_total = sum(balance_map.get(a.id, 0) for a in shared_accts)
    grand_total = sum(balance_map.values())

    return templates.TemplateResponse("accounts.html", {
        "request": request,
        **_common_ctx(db),
        "accts": accts,
        "balance_map": balance_map,
        "per_user_accounts": per_user_accounts,
        "shared_accts": shared_accts,
        "shared_total": shared_total,
        "grand_total": grand_total,
    })
