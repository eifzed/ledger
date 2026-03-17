"""Integration tests for MCP tool functions.

These tests call each tool function directly against an in-memory SQLite
database to verify correct behavior, error handling, and serialization.
Unlike the prompt regression tests (which check LLM output), these test
the actual tool execution path.

Run:
    pytest tests/test_mcp_tools.py -v
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Account, Category, Transaction, User
from app.seed import seed_defaults


# ---------------------------------------------------------------------------
# Test database setup — in-memory SQLite, fresh per test
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    """Create a fresh in-memory database for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()

    seed_defaults(session)

    yield session

    session.close()
    engine.dispose()


@pytest.fixture()
def _patch_db(db, monkeypatch):
    """Monkey-patch the MCP server's _db() context manager to use the test session."""
    from contextlib import contextmanager

    @contextmanager
    def _test_db():
        yield db

    import mcp_server
    monkeypatch.setattr(mcp_server, "_db", _test_db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_user(db, user_id="fazrin", display_name="Fazrin"):
    if not db.query(User).filter(User.id == user_id).first():
        db.add(User(id=user_id, display_name=display_name))
        db.commit()


def _ensure_account(db, account_id, display_name, owner_id, acct_type="bank"):
    if not db.query(Account).filter(Account.id == account_id).first():
        _ensure_user(db, owner_id, owner_id)
        db.add(Account(id=account_id, display_name=display_name, type=acct_type, owner_id=owner_id))
        db.commit()


def _seed_test_accounts(db):
    """Create the standard test accounts for fazrin."""
    _ensure_user(db, "fazrin", "Fazrin")
    for aid, name, atype in [
        ("fazrin_BCA", "BCA", "bank"),
        ("fazrin_JAGO", "Jago", "bank"),
        ("fazrin_CASH", "Cash", "cash"),
    ]:
        _ensure_account(db, aid, name, "fazrin", atype)


# ---------------------------------------------------------------------------
# Transaction tools
# ---------------------------------------------------------------------------


class TestCreateTransaction:

    def test_expense_success(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            category_id="groceries",
            from_account_id="BCA",
            description="test groceries",
        )

        assert "error" not in result
        assert result["transaction"]["user_id"] == "fazrin"
        assert result["transaction"]["amount"] == 50000
        assert result["transaction"]["category_id"] == "groceries"
        assert result["transaction"]["status"] == "posted"
        assert isinstance(result["transaction"]["id"], int)
        assert isinstance(result["balances"], list)
        assert isinstance(result["budget_status"], list)

    def test_expense_missing_account_returns_clarification(self, db, _patch_db):
        import mcp_server
        _ensure_user(db, "fazrin")

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            category_id="groceries",
        )

        assert "error" in result
        assert result["error"]["code"] == "NEEDS_CLARIFICATION"
        details = result["error"]["details"]
        assert any(d.get("field") == "from_account_id" for d in details)

    def test_expense_missing_category_returns_clarification(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            from_account_id="BCA",
        )

        assert "error" in result
        assert result["error"]["code"] == "NEEDS_CLARIFICATION"

    def test_income_success(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="income",
            amount=15000000,
            to_account_id="BCA",
            category_id="salary",
        )

        assert "error" not in result
        assert result["transaction"]["transaction_type"] == "income"
        assert result["transaction"]["amount"] == 15000000

    def test_transfer_success(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="transfer",
            amount=500000,
            from_account_id="BCA",
            to_account_id="JAGO",
        )

        assert "error" not in result
        assert result["transaction"]["transaction_type"] == "transfer"

    def test_invalid_category_returns_error(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            category_id="nonexistent_category",
            from_account_id="BCA",
        )

        assert "error" in result
        assert result["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_account_returns_error(self, db, _patch_db):
        import mcp_server
        _ensure_user(db, "fazrin")

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            category_id="groceries",
            from_account_id="NONEXISTENT",
        )

        assert "error" in result

    def test_auto_creates_user(self, db, _patch_db):
        import mcp_server
        _ensure_account(db, "newuser_CASH", "Cash", "newuser", "cash")

        result = mcp_server.create_transaction(
            user_id="newuser",
            transaction_type="expense",
            amount=10000,
            category_id="groceries",
            from_account_id="CASH",
        )

        assert "error" not in result
        assert db.query(User).filter(User.id == "newuser").first() is not None

    def test_effective_at_with_timezone(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            category_id="groceries",
            from_account_id="BCA",
            effective_at="2026-02-25T14:00:00",
            timezone="Asia/Jakarta",
        )

        assert "error" not in result
        ea = result["transaction"]["effective_at"]
        assert ea is not None

    def test_metadata_stored(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            category_id="groceries",
            from_account_id="BCA",
            metadata={"raw_text": "test message"},
        )

        assert "error" not in result
        txn = db.query(Transaction).filter(Transaction.id == result["transaction"]["id"]).first()
        stored = json.loads(txn.metadata_json)
        assert stored["raw_text"] == "test message"

    def test_response_is_json_serializable(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_transaction(
            user_id="fazrin",
            transaction_type="expense",
            amount=50000,
            category_id="groceries",
            from_account_id="BCA",
        )

        json.dumps(result)


class TestListTransactions:

    def test_empty(self, db, _patch_db):
        import mcp_server
        result = mcp_server.list_transactions()
        assert result["transactions"] == []
        assert result["total"] == 0

    def test_filters_by_user(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=10000, category_id="groceries", from_account_id="BCA",
        )

        result = mcp_server.list_transactions(user_id="fazrin")
        assert result["total"] >= 1

        result = mcp_server.list_transactions(user_id="nobody")
        assert result["total"] == 0


class TestGetTransaction:

    def test_found(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        created = mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=10000, category_id="groceries", from_account_id="BCA",
        )
        txn_id = created["transaction"]["id"]

        result = mcp_server.get_transaction(txn_id)
        assert result["id"] == txn_id
        assert result["amount"] == 10000

    def test_not_found(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_transaction(9999)
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"


class TestVoidTransaction:

    def test_void_success(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        created = mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=10000, category_id="groceries", from_account_id="BCA",
        )
        txn_id = created["transaction"]["id"]

        result = mcp_server.void_transaction(txn_id)
        assert result["status"] == "voided"

    def test_void_not_found(self, db, _patch_db):
        import mcp_server
        result = mcp_server.void_transaction(9999)
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"

    def test_double_void_fails(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        created = mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=10000, category_id="groceries", from_account_id="BCA",
        )
        txn_id = created["transaction"]["id"]

        mcp_server.void_transaction(txn_id)
        result = mcp_server.void_transaction(txn_id)
        assert "error" in result
        assert result["error"]["code"] == "ALREADY_VOIDED"


class TestCorrectTransaction:

    def test_correct_changes_amount(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        created = mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=50000, category_id="groceries", from_account_id="BCA",
        )
        txn_id = created["transaction"]["id"]

        result = mcp_server.correct_transaction(
            txn_id=txn_id,
            user_id="fazrin", transaction_type="expense",
            amount=75000, category_id="groceries", from_account_id="BCA",
        )

        assert "error" not in result
        assert result["transaction"]["amount"] == 75000
        assert result["transaction"]["id"] != txn_id

        original = db.query(Transaction).filter(Transaction.id == txn_id).first()
        assert original.status == "voided"

    def test_correct_not_found(self, db, _patch_db):
        import mcp_server
        result = mcp_server.correct_transaction(
            txn_id=9999, user_id="fazrin",
            transaction_type="expense", amount=10000,
            category_id="groceries", from_account_id="BCA",
        )
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Account tools
# ---------------------------------------------------------------------------


class TestListAccounts:

    def test_returns_seeded_accounts(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.list_accounts()
        assert len(result) >= 3

    def test_filters_by_user(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)
        _ensure_account(db, "magfira_BCA", "BCA", "magfira")

        fazrin_accts = mcp_server.list_accounts(user_id="fazrin")
        magfira_accts = mcp_server.list_accounts(user_id="magfira")

        assert all(a["owner_id"] == "fazrin" for a in fazrin_accts)
        assert all(a["owner_id"] == "magfira" for a in magfira_accts)


class TestGetAccountBalances:

    def test_initial_zero(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.get_account_balances(user_id="fazrin")
        assert len(result) >= 1
        assert all(b["balance"] == 0 for b in result)

    def test_balance_after_income(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        mcp_server.create_transaction(
            user_id="fazrin", transaction_type="income",
            amount=1000000, to_account_id="BCA", category_id="salary",
        )

        result = mcp_server.get_account_balances(user_id="fazrin")
        bca = next(b for b in result if b["account_id"] == "fazrin_BCA")
        assert bca["balance"] == 1000000

    def test_json_serializable(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)
        result = mcp_server.get_account_balances()
        json.dumps(result)


class TestCreateAccount:

    def test_success(self, db, _patch_db):
        import mcp_server
        _ensure_user(db, "fazrin")

        result = mcp_server.create_account(
            id="fazrin_DANA", display_name="Dana",
            type="ewallet", owner_id="fazrin",
        )

        assert "error" not in result
        assert result["id"] == "fazrin_DANA"
        assert result["display_name"] == "Dana"

    def test_duplicate_rejected(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.create_account(
            id="fazrin_BCA", display_name="BCA",
            type="bank", owner_id="fazrin",
        )

        assert "error" in result
        assert result["error"]["code"] == "DUPLICATE"


class TestAdjustAccountBalance:

    def test_credit(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        result = mcp_server.adjust_account_balance(
            account_id="fazrin_BCA", amount=5000000,
            user_id="fazrin", note="Initial balance",
        )

        assert "error" not in result
        assert result["balance"] == 5000000

    def test_debit(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        mcp_server.adjust_account_balance(
            account_id="fazrin_BCA", amount=5000000,
            user_id="fazrin",
        )
        result = mcp_server.adjust_account_balance(
            account_id="fazrin_BCA", amount=-1000000,
            user_id="fazrin",
        )

        assert result["balance"] == 4000000

    def test_nonexistent_account(self, db, _patch_db):
        import mcp_server
        result = mcp_server.adjust_account_balance(
            account_id="nonexistent", amount=1000,
            user_id="fazrin",
        )
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Budget tools
# ---------------------------------------------------------------------------


class TestUpsertBudget:

    def test_create_budget(self, db, _patch_db):
        import mcp_server

        result = mcp_server.upsert_budget(
            month="2026-02", category_id="food", limit_amount=3000000,
        )

        assert "error" not in result
        assert result["category_id"] == "food"
        assert result["limit_amount"] == 3000000

    def test_update_budget(self, db, _patch_db):
        import mcp_server

        mcp_server.upsert_budget(month="2026-02", category_id="food", limit_amount=3000000)
        result = mcp_server.upsert_budget(month="2026-02", category_id="food", limit_amount=4000000)

        assert result["limit_amount"] == 4000000

    def test_subcategory_rejected(self, db, _patch_db):
        import mcp_server

        result = mcp_server.upsert_budget(
            month="2026-02", category_id="groceries", limit_amount=1000000,
        )

        assert "error" in result
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert "subcategory" in result["error"]["message"].lower() or "parent" in result["error"]["message"].lower()

    def test_nonexistent_category(self, db, _patch_db):
        import mcp_server

        result = mcp_server.upsert_budget(
            month="2026-02", category_id="nonexistent", limit_amount=1000000,
        )

        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"


class TestGetBudgetStatus:

    def test_empty_month(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_budget_status(month="2026-02")
        assert result["month"] == "2026-02"
        assert result["budgets"] == []
        assert result["warnings"] == []

    def test_with_budget_and_spending(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        mcp_server.upsert_budget(month="2026-02", category_id="food", limit_amount=1000000)
        mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=800000, category_id="groceries", from_account_id="BCA",
            effective_at="2026-02-15T12:00:00", timezone="Asia/Jakarta",
        )

        result = mcp_server.get_budget_status(month="2026-02")
        assert len(result["budgets"]) >= 1
        food_budget = next(b for b in result["budgets"] if b["category_id"] == "food")
        assert food_budget["used"] == 800000
        assert food_budget["limit"] == 1000000

    def test_json_serializable(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_budget_status(month="2026-02")
        json.dumps(result)


class TestListBudgets:

    def test_empty(self, db, _patch_db):
        import mcp_server
        result = mcp_server.list_budgets(month="2026-02")
        assert result == []

    def test_after_upsert(self, db, _patch_db):
        import mcp_server
        mcp_server.upsert_budget(month="2026-02", category_id="food", limit_amount=3000000)
        result = mcp_server.list_budgets(month="2026-02")
        assert len(result) == 1
        assert result[0]["category_id"] == "food"


class TestGetBudgetHistory:

    def test_empty(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_budget_history(month="2026-02")
        assert result == []

    def test_records_changes(self, db, _patch_db):
        import mcp_server
        mcp_server.upsert_budget(month="2026-02", category_id="food", limit_amount=3000000)
        mcp_server.upsert_budget(month="2026-02", category_id="food", limit_amount=4000000)

        result = mcp_server.get_budget_history(month="2026-02")
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# Summary & metadata tools
# ---------------------------------------------------------------------------


class TestGetMonthlySummary:

    def test_empty_month(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_monthly_summary(month="2026-02")
        assert result["total_expenses"] == 0
        assert result["total_income"] == 0
        assert result["net"] == 0

    def test_with_transactions(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=100000, category_id="groceries", from_account_id="BCA",
            effective_at="2026-02-15T12:00:00", timezone="Asia/Jakarta",
        )
        mcp_server.create_transaction(
            user_id="fazrin", transaction_type="income",
            amount=5000000, to_account_id="BCA", category_id="salary",
            effective_at="2026-02-15T12:00:00", timezone="Asia/Jakarta",
        )

        result = mcp_server.get_monthly_summary(month="2026-02")
        assert result["total_expenses"] == 100000
        assert result["total_income"] == 5000000
        assert result["net"] == 4900000

    def test_json_serializable(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_monthly_summary(month="2026-02")
        json.dumps(result)


class TestGetMetadata:

    def test_returns_expected_keys(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_metadata()
        assert "categories" in result
        assert "accounts" in result
        assert "users" in result
        assert "payment_methods" in result
        assert "transaction_types" in result
        assert "server_time" in result

    def test_categories_seeded(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_metadata()
        cat_ids = [c["id"] for c in result["categories"]]
        assert "food" in cat_ids
        assert "transport" in cat_ids

    def test_json_serializable(self, db, _patch_db):
        import mcp_server
        result = mcp_server.get_metadata()
        json.dumps(result)


class TestHealthCheck:

    def test_ok(self, db, _patch_db):
        import mcp_server
        result = mcp_server.health_check()
        assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# Cross-cutting: account ownership enforcement
# ---------------------------------------------------------------------------


class TestAccountOwnershipEnforcement:
    """Verify the service layer rejects cross-user account usage."""

    def test_cannot_use_other_users_account(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)
        _ensure_account(db, "magfira_BCA", "BCA", "magfira")

        result = mcp_server.create_transaction(
            user_id="magfira",
            transaction_type="expense",
            amount=50000,
            category_id="groceries",
            from_account_id="fazrin_BCA",
        )

        assert "error" in result
        assert "OWNERSHIP" in result["error"]["code"] or "VALIDATION" in result["error"]["code"]


# ---------------------------------------------------------------------------
# Cross-cutting: voided transactions excluded from queries
# ---------------------------------------------------------------------------


class TestVoidedTransactionsExcluded:

    def test_voided_not_in_list(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        created = mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=10000, category_id="groceries", from_account_id="BCA",
        )
        txn_id = created["transaction"]["id"]

        before = mcp_server.list_transactions(user_id="fazrin")
        assert before["total"] == 1

        mcp_server.void_transaction(txn_id)

        after = mcp_server.list_transactions(user_id="fazrin")
        assert after["total"] == 0

    def test_voided_not_in_balance(self, db, _patch_db):
        import mcp_server
        _seed_test_accounts(db)

        mcp_server.adjust_account_balance(
            account_id="fazrin_BCA", amount=1000000, user_id="fazrin",
        )
        created = mcp_server.create_transaction(
            user_id="fazrin", transaction_type="expense",
            amount=100000, category_id="groceries", from_account_id="BCA",
        )
        txn_id = created["transaction"]["id"]

        before = mcp_server.get_account_balances(user_id="fazrin")
        bca_before = next(b for b in before if b["account_id"] == "fazrin_BCA")

        mcp_server.void_transaction(txn_id)

        after = mcp_server.get_account_balances(user_id="fazrin")
        bca_after = next(b for b in after if b["account_id"] == "fazrin_BCA")
        assert bca_after["balance"] > bca_before["balance"]
