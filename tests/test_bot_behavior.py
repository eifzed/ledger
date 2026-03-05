"""Prompt regression tests for the Ledger bot.

Each test sends a Discord-style message through the same prompts OpenClaw uses,
then inspects the curl commands the LLM produces to verify correct behavior.

Run:
    OPENAI_API_KEY=sk-... pytest tests/ -v

Override model:
    TEST_MODEL=gpt-4o pytest tests/ -v
"""

from __future__ import annotations

import pytest

from tests.conftest import ask, ask_multi, parse_curl_body

# ---------------------------------------------------------------------------
# Fake backend responses for multi-turn tests.
# The bot often calls GET endpoints first (accounts, meta) before POSTing.
# These simulate those intermediate responses so the full flow completes.
# ---------------------------------------------------------------------------

META_RESPONSE = '{"server_time": "2026-02-25T14:30:00+07:00", "categories": [{"id":"food","display_name":"Food","parent_id":null},{"id":"groceries","display_name":"Groceries","parent_id":"food"},{"id":"eating_out","display_name":"Eating Out","parent_id":"food"},{"id":"coffee","display_name":"Coffee","parent_id":"food"},{"id":"transport","display_name":"Transport","parent_id":null},{"id":"fuel","display_name":"Fuel","parent_id":"transport"},{"id":"parking","display_name":"Parking","parent_id":"transport"},{"id":"shopping","display_name":"Shopping","parent_id":null},{"id":"income","display_name":"Income","parent_id":null},{"id":"salary","display_name":"Salary","parent_id":"income"}], "accounts": [], "users": [], "payment_methods": ["cash","qris","debit","credit","bank_transfer","ewallet","other"], "transaction_types": ["expense","income","transfer","adjustment"]}'
CONVERT_AUD_25 = '{"from": "AUD", "to": "IDR", "amount": 25, "rate": 11951.70, "result": 298792}'
CONVERT_AUD_788 = '{"from": "AUD", "to": "IDR", "amount": 788, "rate": 11951.70, "result": 9417938}'

FAZRIN_ACCOUNTS = '''[
    {"id": "fazrin_BCA", "display_name": "BCA", "type": "bank", "owner_id": "fazrin"},
    {"id": "fazrin_JAGO", "display_name": "Jago", "type": "bank", "owner_id": "fazrin"},
    {"id": "fazrin_CBA", "display_name": "CBA", "type": "bank", "owner_id": "fazrin"},
    {"id": "fazrin_CASH", "display_name": "Cash", "type": "cash", "owner_id": "fazrin"},
    {"id": "fazrin_GOPAY", "display_name": "GoPay", "type": "ewallet", "owner_id": "fazrin"},
    {"id": "fazrin_OVO", "display_name": "OVO", "type": "ewallet", "owner_id": "fazrin"}
]'''

MAGFIRA_ACCOUNTS = '''[
    {"id": "magfira_BCA", "display_name": "BCA", "type": "bank", "owner_id": "magfira"},
    {"id": "magfira_JAGO", "display_name": "Jago", "type": "bank", "owner_id": "magfira"},
    {"id": "magfira_CBA", "display_name": "CBA", "type": "bank", "owner_id": "magfira"},
    {"id": "magfira_CASH", "display_name": "Cash", "type": "cash", "owner_id": "magfira"},
    {"id": "magfira_GOPAY", "display_name": "GoPay", "type": "ewallet", "owner_id": "magfira"},
    {"id": "magfira_OVO", "display_name": "OVO", "type": "ewallet", "owner_id": "magfira"}
]'''

TRANSACTION_RESPONSE = '''{
    "transaction": {
        "id": 1, "user_id": "fazrin", "transaction_type": "expense",
        "amount": 300000, "category_id": "groceries",
        "from_account_id": "fazrin_JAGO", "to_account_id": null,
        "description": "groceries", "merchant": "Alfamart",
        "payment_method": null, "effective_at": "2026-02-25T07:30:00+00:00",
        "metadata": {"raw_text": "spent 300k on groceries at alfamart via jago"},
        "status": "posted"
    },
    "balances": [], "budget_status": [], "warnings": []
}'''

STANDARD_FAKES = {
    "/v1/meta": META_RESPONSE,
    "/v1/accounts": FAZRIN_ACCOUNTS,
    "/v1/transactions": TRANSACTION_RESPONSE,
}

MAGFIRA_FAKES = {
    "/v1/meta": META_RESPONSE,
    "/v1/accounts": MAGFIRA_ACCOUNTS,
    "/v1/transactions": TRANSACTION_RESPONSE,
}


# ──────────────────────────────────────────────────────────────────────────────
# 1. User ID extraction — the bot must NEVER ask for user_id
# ──────────────────────────────────────────────────────────────────────────────


class TestUserIdExtraction:
    """Bot extracts user_id from [DisplayName] and never asks for it."""

    def test_fazrin_user_id(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] spent 300k on groceries via jago",
            fake_responses=STANDARD_FAKES,
        )
        bodies = resp.curl_bodies()
        assert any(b.get("user_id") == "fazrin" for b in bodies), (
            f"Expected user_id='fazrin' in curl body. Got bodies: {bodies}"
        )

    def test_magfira_user_id(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Magfira] spent 50k on groceries via cash",
            fake_responses=MAGFIRA_FAKES,
        )
        bodies = resp.curl_bodies()
        assert any(b.get("user_id") == "magfira" for b in bodies), (
            f"Expected user_id='magfira' in curl body. Got bodies: {bodies}"
        )

    def test_unknown_user_auto_created(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Ahmad] spent 50k on coffee via dana",
            fake_responses={"/v1/meta": META_RESPONSE, "/v1/accounts": "[]", "/v1/transactions": TRANSACTION_RESPONSE},
        )
        bodies = resp.curl_bodies()
        text = resp.text.lower()
        assert "user_id" not in text, "Bot should not ask for user_id"
        if bodies:
            assert any(b.get("user_id") == "ahmad" for b in bodies)

    def test_never_asks_for_user_id(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] bought coffee 35k via gopay",
            fake_responses=STANDARD_FAKES,
        )
        text = resp.text.lower()
        assert "what is your user" not in text
        assert "what's your user" not in text
        assert "need to know your user" not in text


# ──────────────────────────────────────────────────────────────────────────────
# 2. Account ownership — use the correct user's accounts
# ──────────────────────────────────────────────────────────────────────────────


class TestAccountOwnership:
    """Bot uses the transaction sender's own accounts, never another user's."""

    def test_fazrin_gets_own_account(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] spent 100k on groceries via BCA",
            fake_responses=STANDARD_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        acct = body.get("from_account_id", "")
        assert "magfira" not in acct.lower(), f"Fazrin's txn used magfira's account: {acct}"
        assert acct.lower() in ("bca", "fazrin_bca"), f"Unexpected account: {acct}"

    def test_magfira_gets_own_account(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Magfira] spent 100k on groceries via CBA",
            fake_responses=MAGFIRA_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        acct = body.get("from_account_id", "")
        assert "fazrin" not in acct.lower(), f"Magfira's txn used fazrin's account: {acct}"
        assert acct.lower() in ("cba", "magfira_cba"), f"Unexpected account: {acct}"

    def test_magfira_cash_not_fazrin_cash(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Magfira] spent 20k on snacks via cash",
            fake_responses=MAGFIRA_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        acct = body.get("from_account_id", "")
        assert "fazrin" not in acct.lower(), f"Magfira's cash txn routed to fazrin: {acct}"

    def test_expense_user_and_account_match(self, llm, system_prompt):
        """Person A's expense must have user_id=A AND from_account_id belonging to A."""
        resp = ask_multi(
            llm, system_prompt, "[Magfira] bought groceries for 80k via CBA",
            fake_responses=MAGFIRA_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        assert body.get("user_id") == "magfira", (
            f"user_id should be 'magfira', got '{body.get('user_id')}'"
        )
        acct = body.get("from_account_id", "")
        assert "fazrin" not in acct.lower(), (
            f"Magfira's expense deducted from fazrin's account: {acct}"
        )
        assert acct.lower() in ("cba", "magfira_cba"), (
            f"Expected magfira's CBA, got '{acct}'"
        )

    def test_income_goes_to_correct_person(self, llm, system_prompt):
        """Person B's income must credit to person B's account, not person A's."""
        resp = ask_multi(
            llm, system_prompt, "[Magfira] salary came in 5000 AUD to CBA",
            fake_responses={
                **MAGFIRA_FAKES,
                "/v1/convert": '{"from": "AUD", "to": "IDR", "amount": 5000, "rate": 11951.70, "result": 59758500}',
            },
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        assert body.get("user_id") == "magfira", (
            f"user_id should be 'magfira', got '{body.get('user_id')}'"
        )
        assert body.get("transaction_type") == "income", (
            f"Should be income, got '{body.get('transaction_type')}'"
        )
        to_acct = body.get("to_account_id", "")
        assert "fazrin" not in to_acct.lower(), (
            f"Magfira's salary went to fazrin's account: {to_acct}"
        )
        assert to_acct.lower() in ("cba", "magfira_cba"), (
            f"Expected magfira's CBA for income, got '{to_acct}'"
        )

    def test_fazrin_income_to_own_account(self, llm, system_prompt):
        """Fazrin's income must go to Fazrin's account."""
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] gaji masuk 15jt ke BCA",
            fake_responses=STANDARD_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        assert body.get("user_id") == "fazrin", (
            f"user_id should be 'fazrin', got '{body.get('user_id')}'"
        )
        assert body.get("transaction_type") == "income"
        to_acct = body.get("to_account_id", "")
        assert "magfira" not in to_acct.lower(), (
            f"Fazrin's salary went to magfira's account: {to_acct}"
        )
        assert to_acct.lower() in ("bca", "fazrin_bca"), (
            f"Expected fazrin's BCA for income, got '{to_acct}'"
        )

    def test_magfira_gopay_deducts_from_her_account(self, llm, system_prompt):
        """Magfira using GoPay should deduct from magfira_GOPAY, not fazrin_GOPAY."""
        resp = ask_multi(
            llm, system_prompt, "[Magfira] bought coffee 25k via gopay",
            fake_responses=MAGFIRA_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        assert body.get("user_id") == "magfira", (
            f"user_id should be 'magfira', got '{body.get('user_id')}'"
        )
        acct = body.get("from_account_id", "")
        assert "fazrin" not in acct.lower(), (
            f"Magfira's GoPay txn deducted from fazrin's account: {acct}"
        )
        assert acct.lower() in ("gopay", "magfira_gopay"), (
            f"Expected magfira's GoPay, got '{acct}'"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 3. Amount parsing — shorthands and slang
# ──────────────────────────────────────────────────────────────────────────────


class TestAmountParsing:
    """Bot correctly converts Indonesian amount shorthands to integers."""

    @pytest.mark.parametrize(
        "message, expected_amount",
        [
            ("[Fazrin] spent 300k on groceries via jago", 300000),
            ("[Fazrin] spent 50rb on parking via cash", 50000),
            ("[Fazrin] gaji masuk 15jt ke BCA", 15000000),
            ("[Fazrin] parkir ceban via cash", 10000),
            ("[Fazrin] makan goban via jago", 50000),
            ("[Fazrin] beli snack cepek via cash", 100000),
            ("[Fazrin] beli kopi 2.5k via gopay", 2500),
        ],
        ids=["300k", "50rb", "15jt", "ceban", "goban", "cepek", "2.5k"],
    )
    def test_amount_shorthand(self, llm, system_prompt, message, expected_amount):
        resp = ask_multi(llm, system_prompt, message, fake_responses=STANDARD_FAKES)
        bodies = resp.curl_bodies()
        amounts = [b.get("amount") for b in bodies if "amount" in b]
        assert expected_amount in amounts, (
            f"Expected amount {expected_amount} for '{message}'. Got: {amounts}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 4. Intent detection — correct endpoint for each intent
# ──────────────────────────────────────────────────────────────────────────────


class TestIntentDetection:
    """Bot recognizes user intent and calls the correct API endpoint."""

    def test_expense(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] spent 50k on parking via cash",
            fake_responses=STANDARD_FAKES,
        )
        assert resp.has_curl("POST", "/v1/transactions"), "Should POST to /v1/transactions"

    def test_income(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] gaji masuk 15jt ke BCA",
            fake_responses=STANDARD_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST to /v1/transactions"
        assert body.get("transaction_type") == "income"

    def test_transfer(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] transfer 500k from BCA to Jago",
            fake_responses=STANDARD_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST to /v1/transactions"
        assert body.get("transaction_type") == "transfer"
        assert body.get("from_account_id") is not None
        assert body.get("to_account_id") is not None

    def test_check_balance(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[Fazrin] what's my balance")
        assert resp.has_curl("GET", "/v1/accounts/balances"), "Should GET /v1/accounts/balances"

    def test_budget_status(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[Fazrin] budget status")
        assert resp.has_curl("GET", "/v1/budgets/status"), "Should GET /v1/budgets/status"

    def test_set_budget(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] set food budget to 3jt for this month",
            fake_responses={**STANDARD_FAKES, "/v1/budgets/": '{"month": "2026-02", "category_id": "food", "limit_amount": 3000000}'},
        )
        assert resp.has_curl("PUT", "/v1/budgets/"), "Should PUT to /v1/budgets/"
        body = resp.find_body("PUT", "/v1/budgets/")
        if body:
            assert body.get("limit_amount") == 3000000

    def test_monthly_summary(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[Fazrin] how much did I spend this month")
        assert (
            resp.has_curl("GET", "/v1/summary/monthly")
            or resp.has_curl("GET", "/v1/transactions")
            or resp.has_curl("GET", "/v1/meta")
        ), "Should query summary, transactions, or meta"

    def test_void_transaction(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[Fazrin] cancel #3")
        assert resp.has_curl("POST", "/v1/transactions/3/void"), "Should POST void"

    def test_non_finance_rejected(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[Fazrin] what's the weather today")
        assert len(resp.curls) == 0, "Should not make any API calls for non-finance messages"
        assert resp.text, "Should reply with text explaining scope"


# ──────────────────────────────────────────────────────────────────────────────
# 5. Category inference — bot picks the right subcategory
# ──────────────────────────────────────────────────────────────────────────────


class TestCategoryInference:
    """Bot infers subcategory from description/merchant when obvious."""

    @pytest.mark.parametrize(
        "message, expected_category",
        [
            ("[Fazrin] beli bensin 50k via cash", "fuel"),
            ("[Fazrin] parkir ceban via cash", "parking"),
            ("[Fazrin] beli kopi 35k di starbucks via gopay", "coffee"),
        ],
        ids=["fuel", "parking", "coffee"],
    )
    def test_category_inferred(self, llm, system_prompt, message, expected_category):
        resp = ask_multi(llm, system_prompt, message, fake_responses=STANDARD_FAKES)
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        assert body.get("category_id") == expected_category, (
            f"Expected category '{expected_category}', got '{body.get('category_id')}'"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 6. Time parsing — calls /v1/meta first, correct effective_at
# ──────────────────────────────────────────────────────────────────────────────


class TestTimeParsing:
    """Bot calls /v1/meta for relative times and produces correct effective_at."""

    def test_relative_time_calls_meta_first(self, llm, system_prompt):
        """When user says 'yesterday', bot must call /v1/meta before creating the transaction."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] spent 200k on dinner yesterday 7pm via BCA",
            fake_responses={"/v1/meta": META_RESPONSE, "/v1/transactions": TRANSACTION_RESPONSE},
        )
        curl_order = resp.curls
        meta_idx = next((i for i, c in enumerate(curl_order) if "/v1/meta" in c), None)
        txn_idx = next((i for i, c in enumerate(curl_order) if "POST" in c and "/v1/transactions" in c and "/void" not in c and "/correct" not in c), None)

        assert meta_idx is not None, "Should call /v1/meta for relative time"
        if txn_idx is not None:
            assert meta_idx < txn_idx, "/v1/meta must be called before creating the transaction"

    def test_yesterday_effective_at(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] spent 200k on dinner yesterday 7pm via BCA",
            fake_responses={"/v1/meta": META_RESPONSE, "/v1/transactions": TRANSACTION_RESPONSE},
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "2026-02-24" in ea, f"Yesterday from Feb 25 should be Feb 24, got {ea}"
            assert "19:00" in ea or "T19:" in ea, f"7pm should be 19:00, got {ea}"

    def test_no_time_omits_effective_at(self, llm, system_prompt):
        """When no time is specified, effective_at should be omitted (backend defaults to now)."""
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] spent 50k on parking via cash",
            fake_responses=STANDARD_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body:
            assert body.get("effective_at") is None, (
                f"No time specified, but effective_at was set to {body.get('effective_at')}"
            )

    def test_explicit_time_today(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] bought coffee 35k via gopay at 5am",
            fake_responses={"/v1/meta": META_RESPONSE, "/v1/transactions": TRANSACTION_RESPONSE},
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "05:00" in ea or "T05:" in ea, f"5am should be 05:00, got {ea}"

    def test_two_days_ago(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] bought groceries 300k via jago 2 days ago",
            fake_responses={"/v1/meta": META_RESPONSE, "/v1/transactions": TRANSACTION_RESPONSE},
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "2026-02-23" in ea, f"2 days before Feb 25 should be Feb 23, got {ea}"


# ──────────────────────────────────────────────────────────────────────────────
# 7. Timezone — Magfira uses Australia/Sydney
# ──────────────────────────────────────────────────────────────────────────────


class TestTimezone:
    """Timezone handling: each user gets their own offset, API returns UTC."""

    def test_magfira_timezone(self, llm, system_prompt):
        """Magfira's times should use Australia/Sydney (+11:00)."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[Magfira] spent 50k on groceries via cash at 3pm",
            fake_responses={"/v1/meta": META_RESPONSE, "/v1/transactions": TRANSACTION_RESPONSE},
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "+11:00" in ea or "+11" in ea, (
                f"Magfira should use Australia/Sydney timezone, got {ea}"
            )

    def test_fazrin_uses_jakarta_timezone(self, llm, system_prompt):
        """Fazrin's times should use Asia/Jakarta (+07:00)."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] bought coffee 15k via cash at 9am",
            fake_responses=STANDARD_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "+07:00" in ea or "+07" in ea, (
                f"Fazrin should use Asia/Jakarta timezone, got {ea}"
            )

    def test_magfira_yesterday_uses_sydney_offset(self, llm, system_prompt):
        """Relative time ('yesterday') for Magfira should still carry +11:00."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[Magfira] bought groceries 30k via cash yesterday 2pm",
            fake_responses={
                "/v1/meta": META_RESPONSE,
                "/v1/accounts": MAGFIRA_ACCOUNTS,
                "/v1/transactions": TRANSACTION_RESPONSE,
            },
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "+11:00" in ea or "+11" in ea, (
                f"Magfira's relative time should use Sydney offset, got {ea}"
            )
            assert "2026-02-24" in ea, (
                f"Yesterday from Feb 25 should be Feb 24, got {ea}"
            )

    def test_unknown_user_defaults_to_jakarta(self, llm, system_prompt):
        """Unknown users should default to Jakarta timezone (+07:00)."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[Budi] spent 25k on parking via cash at 8am",
            fake_responses={"/v1/meta": META_RESPONSE, "/v1/transactions": TRANSACTION_RESPONSE},
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "+07:00" in ea or "+07" in ea, (
                f"Unknown user should default to Jakarta timezone, got {ea}"
            )

    def test_revision_with_utc_response(self, llm, system_prompt):
        """When the bot reads back a UTC effective_at from the API during a revision,
        it should not be confused and should correctly apply the new time with the
        user's local offset."""
        utc_txn = '''{
            "id": 5, "user_id": "magfira", "transaction_type": "expense",
            "amount": 30000, "category_id": "groceries",
            "from_account_id": "magfira_CASH", "to_account_id": null,
            "description": "groceries", "merchant": null,
            "payment_method": null, "effective_at": "2026-02-25T04:00:00+00:00",
            "metadata": {}, "status": "posted"
        }'''
        resp = ask_multi(
            llm,
            system_prompt,
            "[Magfira] fix #5 should be 6pm",
            fake_responses={
                "/v1/meta": META_RESPONSE,
                "/v1/transactions/5": utc_txn,
                "/v1/transactions/5/correct": TRANSACTION_RESPONSE,
            },
        )
        body = resp.find_body("POST", "/v1/transactions/5/correct")
        if body and body.get("effective_at"):
            ea = body["effective_at"]
            assert "+11:00" in ea or "+11" in ea, (
                f"Magfira's revised time should use Sydney offset, got {ea}"
            )
            assert "18:00" in ea or "T18:" in ea, (
                f"6pm should be 18:00 local, got {ea}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 8. Foreign currency conversion — calls /v1/convert, uses result
# ──────────────────────────────────────────────────────────────────────────────


class TestCurrencyConversion:
    """Bot calls /v1/convert for foreign currencies and uses the result directly."""

    def test_aud_calls_convert_endpoint(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Magfira] bought lunch for 25 AUD via CBA",
            fake_responses={
                "/v1/convert": CONVERT_AUD_25,
                "/v1/transactions": TRANSACTION_RESPONSE,
                "/v1/meta": META_RESPONSE,
            },
        )
        assert resp.has_curl("GET", "/v1/convert"), "Should call /v1/convert for AUD"

    def test_convert_uses_result_not_manual_calc(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Magfira] bought lunch for 25 AUD via CBA",
            fake_responses={
                "/v1/convert": CONVERT_AUD_25,
                "/v1/transactions": TRANSACTION_RESPONSE,
                "/v1/meta": META_RESPONSE,
            },
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body:
            assert body.get("amount") == 298792, (
                f"Should use convert result 298792, got {body.get('amount')}"
            )

    def test_convert_stores_original_in_metadata(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Magfira] bought lunch for 25 AUD via CBA",
            fake_responses={
                "/v1/convert": CONVERT_AUD_25,
                "/v1/transactions": TRANSACTION_RESPONSE,
                "/v1/meta": META_RESPONSE,
            },
        )
        body = resp.find_body("POST", "/v1/transactions")
        if body:
            meta = body.get("metadata", {})
            assert meta.get("original_amount") == 25 or meta.get("original_amount") == 25.0
            assert meta.get("original_currency") == "AUD"

    def test_budget_in_foreign_currency(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Magfira] set food budget to 788 AUD",
            fake_responses={
                "/v1/convert": CONVERT_AUD_788,
                "/v1/budgets/": '{"month": "2026-02", "category_id": "food", "limit_amount": 9417938}',
                "/v1/meta": META_RESPONSE,
            },
        )
        assert resp.has_curl("GET", "/v1/convert"), "Should convert AUD to IDR first"
        body = resp.find_body("PUT", "/v1/budgets/")
        if body:
            assert body.get("limit_amount") == 9417938, (
                f"Budget should use converted amount 9417938, got {body.get('limit_amount')}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 9. Revision flow — fetch original first, copy all fields
# ──────────────────────────────────────────────────────────────────────────────

GET_TXN_1_RESPONSE = '''{
    "id": 1, "user_id": "fazrin", "transaction_type": "expense",
    "amount": 300000, "category_id": "groceries",
    "from_account_id": "fazrin_JAGO", "to_account_id": null,
    "description": "groceries", "merchant": "Alfamart",
    "payment_method": null, "effective_at": "2026-02-25T07:30:00+00:00",
    "metadata": {"raw_text": "spent 300k on groceries at alfamart via jago"},
    "status": "posted"
}'''


class TestRevisionFlow:
    """Bot fetches the original transaction first and only changes requested fields."""

    def test_revision_fetches_original_first(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] fix #1 should be 350k",
            fake_responses={
                "/v1/transactions/1": GET_TXN_1_RESPONSE,
                "/correct": TRANSACTION_RESPONSE,
            },
        )
        curl_order = resp.curls
        get_idx = next((i for i, c in enumerate(curl_order) if "GET" in c and "/v1/transactions/1" in c), None)
        correct_idx = next((i for i, c in enumerate(curl_order) if "POST" in c and "/correct" in c), None)

        assert get_idx is not None, "Should GET the original transaction first"
        if correct_idx is not None:
            assert get_idx < correct_idx, "GET original must come before POST correct"

    def test_revision_changes_only_amount(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] fix #1 should be 350k",
            fake_responses={
                "/v1/transactions/1": GET_TXN_1_RESPONSE,
                "/correct": TRANSACTION_RESPONSE,
            },
        )
        body = resp.find_body("POST", "/correct")
        if body:
            assert body.get("amount") == 350000, f"Amount should be 350000, got {body.get('amount')}"
            assert body.get("category_id") == "groceries", "Category should carry over from original"
            assert body.get("from_account_id") is not None, "Account should carry over from original"

    def test_revision_does_not_ask_unnecessary_questions(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] fix #1 should be 350k",
            fake_responses={
                "/v1/transactions/1": GET_TXN_1_RESPONSE,
                "/correct": TRANSACTION_RESPONSE,
            },
        )
        text = resp.text.lower()
        assert "category" not in text or "groceries" in text, "Should not ask about category"
        assert "which account" not in text, "Should not ask about account"

    def test_revision_time_only(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[Fazrin] change #1 to yesterday 5pm",
            fake_responses={
                "/v1/transactions/1": GET_TXN_1_RESPONSE,
                "/v1/meta": META_RESPONSE,
                "/correct": TRANSACTION_RESPONSE,
            },
        )
        body = resp.find_body("POST", "/correct")
        if body:
            assert body.get("amount") == 300000, "Amount should stay 300000"
            assert body.get("category_id") == "groceries", "Category should stay groceries"
            ea = body.get("effective_at", "")
            assert "2026-02-24" in ea, f"Yesterday should be Feb 24, got {ea}"


# ──────────────────────────────────────────────────────────────────────────────
# 10. Clarification — asks with options, only when truly needed
# ──────────────────────────────────────────────────────────────────────────────


class TestClarification:
    """Bot asks specific clarification questions when required fields are missing."""

    def test_asks_account_when_missing(self, llm, system_prompt):
        """Fazrin has multiple accounts — bot should ask which one."""
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] beli bensin 50k",
            fake_responses=STANDARD_FAKES, max_turns=2,
        )
        text = resp.text.lower()
        has_post = resp.has_curl("POST", "/v1/transactions")
        if not has_post and text:
            has_options = any(kw in text for kw in ["bca", "jago", "cash", "gopay", "ovo"])
            assert has_options, (
                f"Should offer account options when from_account is missing. Got: {resp.text}"
            )

    def test_qris_still_needs_account(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] beli kopi 35k qris",
            fake_responses=STANDARD_FAKES, max_turns=2,
        )
        text = resp.text.lower()
        has_post = resp.has_curl("POST", "/v1/transactions")
        if not has_post and text:
            assert "qris" in text or any(
                kw in text for kw in ["bca", "jago", "gopay", "ovo"]
            ), "Should ask which account the QRIS was charged to"

    def test_fully_specified_no_clarification(self, llm, system_prompt):
        """When all fields are present, bot should not ask any questions."""
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] transfer 500k from BCA to Jago",
            fake_responses=STANDARD_FAKES,
        )
        assert resp.has_curl("POST", "/v1/transactions"), (
            "All fields specified — should create transaction directly, not ask questions"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 11. Safety — things the bot must NEVER do
# ──────────────────────────────────────────────────────────────────────────────


class TestSafety:
    """Bot must never do dangerous things."""

    def test_never_uses_web_fetch(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] what's my balance",
            fake_responses=STANDARD_FAKES,
        )
        for cmd in resp.all_commands:
            assert "web_fetch" not in cmd, "Must never use web_fetch — only exec with curl"

    def test_always_includes_api_key(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] spent 100k on groceries via BCA",
            fake_responses=STANDARD_FAKES,
        )
        for curl in resp.curls:
            assert "X-API-Key" in curl, f"Every curl must include X-API-Key header. Got: {curl}"

    def test_no_finance_api_as_command(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] spent 50k on parking via cash",
            fake_responses=STANDARD_FAKES,
        )
        for cmd in resp.all_commands:
            assert not cmd.startswith("finance-api"), (
                f"Must not run 'finance-api' as a CLI command. Got: {cmd}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 12. Metadata — raw_text stored for audit
# ──────────────────────────────────────────────────────────────────────────────


class TestMetadata:
    """Bot includes metadata.raw_text in every transaction."""

    def test_raw_text_included(self, llm, system_prompt):
        msg = "spent 300k on groceries at alfamart via jago"
        resp = ask_multi(
            llm, system_prompt, f"[Fazrin] {msg}",
            fake_responses=STANDARD_FAKES,
        )
        body = resp.find_body("POST", "/v1/transactions")
        assert body is not None, "Should POST a transaction"
        meta = body.get("metadata", {})
        assert "raw_text" in meta, "metadata.raw_text should be included"
        assert msg in meta["raw_text"] or "groceries" in meta.get("raw_text", ""), (
            f"raw_text should contain the original message"
        )
