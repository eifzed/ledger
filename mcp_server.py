"""Ledger finance tool server.

Exposes the same operations as the FastAPI REST endpoints, but as
structured tool functions that an AI agent can invoke directly.  Each
tool wraps the service layer — no HTTP round-trip needed.

CLI mode (used by OpenClaw via exec):
    python mcp_server.py <tool_name> ['<json_args>']
    python mcp_server.py health_check
    python mcp_server.py create_transaction '{"user_id":"fazrin","amount":50000,...}'

MCP mode (for future use when OpenClaw adds native MCP support):
    python mcp_server.py --mcp
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import httpx
from fastmcp import FastMCP

from app.database import Base, SessionLocal, engine
from app.errors import LedgerHTTPException, NeedsClarificationError
from app.models import Account, Category, Transaction, User
from app.schemas import (
    AccountBalance,
    AccountOut,
    BudgetOut,
    BudgetSnapshotOut,
    CategoryChild,
    CategoryOut,
    PaymentMethod,
    TransactionCreate,
    TransactionOut,
    TransactionType,
    UserOut,
)
from app.services import account_service, budget_service, summary_service, transaction_service
from app.tz import now_jakarta, now_utc

def _init_database():
    """Create tables and seed defaults on first run."""
    Base.metadata.create_all(bind=engine)
    from app.seed import seed_defaults
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()


mcp = FastMCP(
    "ledger",
    instructions=(
        "Household finance API. Use these tools to log transactions, "
        "manage budgets, check balances, and get summaries. "
        "All amounts are in IDR (integers). "
        "Use convert_currency for foreign currencies before logging."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RATE_API = "https://open.er-api.com/v6/latest"


@contextmanager
def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize_txn(txn: Transaction) -> dict:
    return TransactionOut.model_validate(txn).model_dump(mode="json")


def _error_dict(code: str, message: str, details: list[dict] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


def _run_tool(fn, *args, **kwargs) -> dict | list | Any:
    """Call a service function, catching Ledger-specific exceptions."""
    try:
        return fn(*args, **kwargs)
    except NeedsClarificationError as exc:
        return _error_dict(
            "NEEDS_CLARIFICATION",
            exc.message,
            [d.model_dump(exclude_none=True) for d in exc.details],
        )
    except LedgerHTTPException as exc:
        return _error_dict(
            exc.code,
            exc.error_message,
            [d.model_dump(exclude_none=True) for d in exc.details],
        )


# ---------------------------------------------------------------------------
# Transaction tools
# ---------------------------------------------------------------------------


@mcp.tool()
def create_transaction(
    user_id: str,
    transaction_type: str,
    amount: float,
    category_id: str | None = None,
    from_account_id: str | None = None,
    to_account_id: str | None = None,
    description: str | None = None,
    merchant: str | None = None,
    payment_method: str | None = None,
    effective_at: str | None = None,
    timezone: str | None = None,
    note: str | None = None,
    metadata: dict | None = None,
    currency: str = "IDR",
) -> dict:
    """Create a financial transaction (expense, income, transfer, or adjustment).

    Returns the created transaction with its integer ID, updated account
    balances, budget status, and any warnings.

    Required fields by type:
    - expense: user_id, amount, category_id, from_account_id
    - income: user_id, amount, to_account_id
    - transfer: user_id, amount, from_account_id, to_account_id
    - adjustment: user_id, amount

    Send effective_at as ISO 8601 naive local time (no offset) with timezone
    as an IANA name (e.g. "Asia/Jakarta"). The backend converts to UTC.
    Omit both to default to now.
    """
    with _db() as db:
        ea = datetime.fromisoformat(effective_at) if effective_at else None
        try:
            data = TransactionCreate(
                user_id=user_id,
                transaction_type=TransactionType(transaction_type),
                amount=amount,
                currency=currency,
                category_id=category_id,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                description=description,
                merchant=merchant,
                payment_method=PaymentMethod(payment_method) if payment_method else None,
                effective_at=ea,
                timezone=timezone,
                note=note,
                metadata=metadata,
            )
        except NeedsClarificationError as exc:
            return _error_dict(
                "NEEDS_CLARIFICATION",
                exc.message,
                [d.model_dump(exclude_none=True) for d in exc.details],
            )
        except Exception as exc:
            return _error_dict("VALIDATION_ERROR", str(exc))

        result = _run_tool(transaction_service.create_transaction, db, data)
        if isinstance(result, dict) and "error" in result:
            return result

        return {
            "transaction": _serialize_txn(result["transaction"]),
            "balances": [b.model_dump(mode="json") for b in result["balances"]],
            "budget_status": [b.model_dump(mode="json") for b in result["budget_status"]],
            "warnings": [w.model_dump(mode="json") for w in result["warnings"]],
        }


@mcp.tool()
def list_transactions(
    month: str | None = None,
    user_id: str | None = None,
    category_id: str | None = None,
    account_id: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List transactions with optional filters.

    month: YYYY-MM format. category_id: filter by category (includes
    subcategories). limit: 1-200, default 50.
    """
    with _db() as db:
        result = _run_tool(
            transaction_service.list_transactions,
            db,
            month=month,
            user_id=user_id,
            category_id=category_id,
            account_id=account_id,
            search=search,
            limit=min(limit, 200),
            offset=max(offset, 0),
        )
        if isinstance(result, dict) and "error" in result:
            return result

        rows, total = result
        return {
            "transactions": [_serialize_txn(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@mcp.tool()
def get_transaction(txn_id: int) -> dict:
    """Get a single transaction by its integer ID."""
    with _db() as db:
        txn = transaction_service.get_transaction(db, txn_id)
        if txn is None:
            return _error_dict("NOT_FOUND", "Transaction not found")
        return _serialize_txn(txn)


@mcp.tool()
def void_transaction(txn_id: int) -> dict:
    """Void (cancel) a transaction. Irreversible — sets status to 'voided'."""
    with _db() as db:
        result = _run_tool(transaction_service.void_transaction, db, txn_id)
        if isinstance(result, dict) and "error" in result:
            return result
        return _serialize_txn(result)


@mcp.tool()
def correct_transaction(
    txn_id: int,
    user_id: str,
    transaction_type: str,
    amount: float,
    category_id: str | None = None,
    from_account_id: str | None = None,
    to_account_id: str | None = None,
    description: str | None = None,
    merchant: str | None = None,
    payment_method: str | None = None,
    effective_at: str | None = None,
    timezone: str | None = None,
    note: str | None = None,
    metadata: dict | None = None,
    currency: str = "IDR",
) -> dict:
    """Correct a transaction: voids the original and creates a replacement.

    Fetch the original first with get_transaction, copy ALL fields, then
    override only the fields the user wants to change.  The body schema
    is identical to create_transaction.
    """
    with _db() as db:
        ea = datetime.fromisoformat(effective_at) if effective_at else None
        try:
            data = TransactionCreate(
                user_id=user_id,
                transaction_type=TransactionType(transaction_type),
                amount=amount,
                currency=currency,
                category_id=category_id,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                description=description,
                merchant=merchant,
                payment_method=PaymentMethod(payment_method) if payment_method else None,
                effective_at=ea,
                timezone=timezone,
                note=note,
                metadata=metadata,
            )
        except NeedsClarificationError as exc:
            return _error_dict(
                "NEEDS_CLARIFICATION",
                exc.message,
                [d.model_dump(exclude_none=True) for d in exc.details],
            )
        except Exception as exc:
            return _error_dict("VALIDATION_ERROR", str(exc))

        result = _run_tool(transaction_service.correct_transaction, db, txn_id, data)
        if isinstance(result, dict) and "error" in result:
            return result

        return {
            "transaction": _serialize_txn(result["transaction"]),
            "balances": [b.model_dump(mode="json") for b in result["balances"]],
            "budget_status": [b.model_dump(mode="json") for b in result["budget_status"]],
            "warnings": [w.model_dump(mode="json") for w in result["warnings"]],
        }


# ---------------------------------------------------------------------------
# Account tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_accounts(user_id: str | None = None) -> list[dict]:
    """List accounts, optionally filtered by user_id (owner).

    You can send just the display name (e.g. "Cash", "BCA") as an account
    ID when creating transactions — the backend resolves it to the user's
    own prefixed account automatically.
    """
    with _db() as db:
        accounts = account_service.list_accounts(db, owner_id=user_id)
        return [AccountOut.model_validate(a).model_dump(mode="json") for a in accounts]


@mcp.tool()
def get_account_balances(user_id: str | None = None) -> list[dict]:
    """Get current balance for each active account.

    Omit user_id for household-wide balances.
    """
    with _db() as db:
        balances = account_service.compute_balances(db, owner_id=user_id)
        return [b.model_dump(mode="json") for b in balances]


@mcp.tool()
def create_account(
    id: str,
    display_name: str,
    type: str,
    owner_id: str | None = None,
    currency: str = "IDR",
) -> dict:
    """Create a new account.

    id: unique ID, convention is owner_SHORTNAME (e.g. 'fazrin_DANA').
    type: bank | cash | ewallet | credit_card | other.
    owner_id: user who owns this account.
    """
    with _db() as db:
        existing = account_service.get_account(db, id)
        if existing:
            return _error_dict("DUPLICATE", f"Account '{id}' already exists")

        if owner_id and not db.query(User).filter(User.id == owner_id).first():
            db.add(User(id=owner_id, display_name=owner_id))
            db.flush()

        result = _run_tool(
            account_service.create_account,
            db, id, display_name, type, currency, owner_id,
        )
        if isinstance(result, dict) and "error" in result:
            return result

        return AccountOut.model_validate(result).model_dump(mode="json")


@mcp.tool()
def adjust_account_balance(
    account_id: str,
    amount: float,
    user_id: str,
    note: str | None = None,
) -> dict:
    """Adjust an account's balance directly.

    Positive amount = credit (add money), negative = debit (remove money).
    Creates an adjustment transaction under the hood.
    """
    with _db() as db:
        acct = account_service.get_account(db, account_id)
        if not acct:
            return _error_dict("NOT_FOUND", f"Account '{account_id}' not found")

        if not db.query(User).filter(User.id == user_id).first():
            db.add(User(id=user_id, display_name=user_id))
            db.flush()

        txn = Transaction(
            effective_at=now_utc(),
            user_id=user_id,
            transaction_type="adjustment",
            amount=abs(round(amount)),
            currency=acct.currency,
            description=f"Balance adjustment for {acct.display_name}",
            to_account_id=account_id if amount >= 0 else None,
            from_account_id=account_id if amount < 0 else None,
            note=note,
            status="posted",
        )
        db.add(txn)
        db.commit()

        balance = account_service.compute_single_balance(db, account_id)
        return AccountBalance(
            account_id=account_id,
            display_name=acct.display_name,
            owner_id=acct.owner_id,
            balance=balance,
        ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Budget tools
# ---------------------------------------------------------------------------


@mcp.tool()
def upsert_budget(
    month: str,
    category_id: str,
    limit_amount: int,
    scope_user_id: str | None = None,
) -> dict:
    """Set or update a budget for a parent category in a given month.

    month: YYYY-MM format. category_id must be a parent category (e.g.
    'food', not 'groceries'). scope_user_id: null = household budget.
    """
    with _db() as db:
        cat = db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            return _error_dict("NOT_FOUND", f"Category '{category_id}' not found")
        if cat.parent_id is not None:
            return _error_dict(
                "VALIDATION_ERROR",
                f"Budgets must target a parent category. "
                f"'{category_id}' is a subcategory of '{cat.parent_id}'.",
            )

        result = _run_tool(
            budget_service.upsert_budget,
            db,
            month=month,
            category_id=category_id,
            limit_amount=limit_amount,
            scope_user_id=scope_user_id,
        )
        if isinstance(result, dict) and "error" in result:
            return result

        return BudgetOut.model_validate(result).model_dump(mode="json")


@mcp.tool()
def list_budgets(month: str) -> list[dict]:
    """List all budgets for a month (YYYY-MM)."""
    with _db() as db:
        budgets = budget_service.list_budgets(db, month)
        return [BudgetOut.model_validate(b).model_dump(mode="json") for b in budgets]


@mcp.tool()
def get_budget_status(month: str | None = None) -> dict:
    """Get budget usage, remaining amount, percent, and warnings per category.

    Defaults to the current month if omitted.
    """
    with _db() as db:
        if not month:
            month = now_jakarta().strftime("%Y-%m")
        items, warnings = budget_service.compute_budget_status(db, month)
        return {
            "month": month,
            "budgets": [i.model_dump(mode="json") for i in items],
            "warnings": [w.model_dump(mode="json") for w in warnings],
        }


@mcp.tool()
def get_budget_history(month: str, limit: int = 50) -> list[dict]:
    """Get budget change history for a month."""
    with _db() as db:
        snaps = budget_service.list_snapshots(db, month, limit=min(limit, 200))
        return [BudgetSnapshotOut.model_validate(s).model_dump(mode="json") for s in snaps]


# ---------------------------------------------------------------------------
# Summary & metadata tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_monthly_summary(month: str | None = None, user_id: str | None = None) -> dict:
    """Get a spending summary for a month.

    Returns total expenses, total income, net, breakdown by category
    and user, daily totals, top merchants, budget status, and warnings.
    Omit user_id for household-wide summary.
    """
    with _db() as db:
        if not month:
            month = now_jakarta().strftime("%Y-%m")
        result = summary_service.monthly_summary(db, month, user_id=user_id)
        return result.model_dump(mode="json")


@mcp.tool()
def get_metadata() -> dict:
    """Get all categories, accounts, users, payment methods, transaction
    types, and the current server time.

    Call this to discover valid IDs and to get the current date/time
    for resolving relative time expressions like 'yesterday'.
    """
    with _db() as db:
        parents = (
            db.query(Category)
            .filter(Category.is_active == 1, Category.parent_id.is_(None))
            .order_by(Category.display_name)
            .all()
        )

        categories_out = []
        for p in parents:
            children = (
                db.query(Category)
                .filter(Category.is_active == 1, Category.parent_id == p.id)
                .order_by(Category.display_name)
                .all()
            )
            categories_out.append(
                CategoryOut(
                    id=p.id,
                    display_name=p.display_name,
                    parent_id=None,
                    is_active=bool(p.is_active),
                    children=[CategoryChild.model_validate(c) for c in children],
                ).model_dump(mode="json")
            )

        accounts = (
            db.query(Account).filter(Account.is_active == 1)
            .order_by(Account.display_name).all()
        )
        users = db.query(User).order_by(User.display_name).all()

        return {
            "categories": categories_out,
            "accounts": [AccountOut.model_validate(a).model_dump(mode="json") for a in accounts],
            "users": [UserOut.model_validate(u).model_dump(mode="json") for u in users],
            "payment_methods": [m.value for m in PaymentMethod],
            "transaction_types": [t.value for t in TransactionType],
            "server_time": now_jakarta().isoformat(),
        }


@mcp.tool()
def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str = "IDR",
) -> dict:
    """Convert an amount from one currency to another using live exchange rates.

    Always use this for foreign currency amounts (AUD, USD, SGD, etc.)
    before logging a transaction.  Use the 'result' field directly as
    the IDR amount — never calculate the conversion yourself.
    """
    from_code = from_currency.upper()
    to_code = to_currency.upper()

    if from_code == to_code:
        return {"from": from_code, "to": to_code, "amount": amount, "rate": 1.0, "result": round(amount)}

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{_RATE_API}/{from_code}")
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return _error_dict("CONVERSION_ERROR", f"Failed to fetch exchange rate: {exc}")

    if data.get("result") != "success":
        return _error_dict("CONVERSION_ERROR", f"Exchange rate API error: {data.get('error-type', 'unknown')}")

    rates = data.get("rates", {})
    if to_code not in rates:
        return _error_dict("VALIDATION_ERROR", f"Unknown target currency: {to_code}")

    rate = rates[to_code]
    result = round(amount * rate)

    return {"from": from_code, "to": to_code, "amount": amount, "rate": rate, "result": result}


@mcp.tool()
def health_check() -> dict:
    """Check if the Ledger backend is operational."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# CLI registry & entry point
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: dict[str, Any] = {
    "create_transaction": create_transaction,
    "list_transactions": list_transactions,
    "get_transaction": get_transaction,
    "void_transaction": void_transaction,
    "correct_transaction": correct_transaction,
    "list_accounts": list_accounts,
    "get_account_balances": get_account_balances,
    "create_account": create_account,
    "adjust_account_balance": adjust_account_balance,
    "upsert_budget": upsert_budget,
    "list_budgets": list_budgets,
    "get_budget_status": get_budget_status,
    "get_budget_history": get_budget_history,
    "get_monthly_summary": get_monthly_summary,
    "get_metadata": get_metadata,
    "convert_currency": convert_currency,
    "health_check": health_check,
}


def _cli_main() -> None:
    """CLI entrypoint: mcp_server.py <tool_name> [json_args]"""
    tool_name = sys.argv[1]

    if tool_name not in _TOOL_REGISTRY:
        print(json.dumps(_error_dict(
            "UNKNOWN_TOOL",
            f"Unknown tool: {tool_name}. "
            f"Available: {', '.join(sorted(_TOOL_REGISTRY))}",
        )))
        sys.exit(1)

    kwargs: dict[str, Any] = {}
    if len(sys.argv) > 2:
        try:
            kwargs = json.loads(sys.argv[2])
        except json.JSONDecodeError as exc:
            print(json.dumps(_error_dict("PARSE_ERROR", f"Invalid JSON: {exc}")))
            sys.exit(1)

    try:
        result = _TOOL_REGISTRY[tool_name](**kwargs)
    except TypeError as exc:
        print(json.dumps(_error_dict("ARG_ERROR", str(exc))))
        sys.exit(1)
    except Exception as exc:
        print(json.dumps(_error_dict("INTERNAL_ERROR", str(exc))))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    _init_database()
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":
        mcp.run(transport="stdio")
    elif len(sys.argv) > 1:
        _cli_main()
    else:
        print(json.dumps({"tools": sorted(_TOOL_REGISTRY.keys())}))
        sys.exit(0)
