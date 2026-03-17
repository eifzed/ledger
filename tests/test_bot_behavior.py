"""Prompt regression tests for the Ledger bot.

Each test sends messages through the same prompts OpenClaw uses, then inspects
the structured MCP tool calls the LLM produces to verify correct behavior.

Messages use the OpenClaw sender label format: [from: DisplayName] message...
Some tests also verify the legacy [DisplayName] format works as a fallback.

Run:
    OPENAI_API_KEY=sk-... pytest tests/ -v

Override model:
    TEST_MODEL=gpt-4o pytest tests/ -v
"""

from __future__ import annotations

import pytest

from tests.conftest import ask, ask_multi


def _has_sydney_tz(args: dict) -> bool:
    """Check if the tool call arguments target Australia/Sydney."""
    tz = args.get("timezone", "")
    ea = args.get("effective_at", "")
    return (
        "sydney" in tz.lower()
        or "australia" in tz.lower()
        or "+11:00" in ea
        or "+10:00" in ea
        or ("+11" in ea.split("T")[-1] if "T" in ea else False)
    )


def _has_jakarta_tz(args: dict) -> bool:
    """Check if the tool call arguments target Asia/Jakarta (or is default)."""
    tz = args.get("timezone", "")
    ea = args.get("effective_at", "")
    if not tz:
        return True
    return "jakarta" in tz.lower() or "asia" in tz.lower() or "+07:00" in ea

# ---------------------------------------------------------------------------
# Fake backend responses for multi-turn tests.
# The bot often calls GET tools first (list_accounts, get_metadata) before
# calling create_transaction. These simulate those intermediate responses.
# ---------------------------------------------------------------------------

_CATEGORIES_JSON = '[{"id":"food","display_name":"Food","parent_id":null},{"id":"groceries","display_name":"Groceries","parent_id":"food"},{"id":"eating_out","display_name":"Eating Out","parent_id":"food"},{"id":"coffee","display_name":"Coffee","parent_id":"food"},{"id":"transport","display_name":"Transport","parent_id":null},{"id":"fuel","display_name":"Fuel","parent_id":"transport"},{"id":"parking","display_name":"Parking","parent_id":"transport"},{"id":"shopping","display_name":"Shopping","parent_id":null},{"id":"income","display_name":"Income","parent_id":null},{"id":"salary","display_name":"Salary","parent_id":"income"}]'
_META_TEMPLATE = '{{"server_time": "{server_time}", "categories": __CATS__, "accounts": [], "users": [], "payment_methods": ["cash","qris","debit","credit","bank_transfer","ewallet","other"], "transaction_types": ["expense","income","transfer","adjustment"]}}'


def _build_meta(server_time: str) -> str:
    return _META_TEMPLATE.format(server_time=server_time).replace("__CATS__", _CATEGORIES_JSON)


META_RESPONSE = _build_meta("2026-02-25T14:30:00+07:00")
META_RESPONSE_AEST = _build_meta("2026-07-15T14:30:00+07:00")
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
    "get_metadata": META_RESPONSE,
    "list_accounts": FAZRIN_ACCOUNTS,
    "create_transaction": TRANSACTION_RESPONSE,
}

MAGFIRA_FAKES = {
    "get_metadata": META_RESPONSE,
    "list_accounts": MAGFIRA_ACCOUNTS,
    "create_transaction": TRANSACTION_RESPONSE,
}


# ──────────────────────────────────────────────────────────────────────────────
# 1. User ID extraction — the bot must NEVER ask for user_id
# ──────────────────────────────────────────────────────────────────────────────


class TestUserIdExtraction:
    """Bot extracts user_id from sender label and never asks for it."""

    def test_fazrin_user_id(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] spent 300k on groceries via jago",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "fazrin", (
            f"Expected user_id='fazrin'. Got: {args.get('user_id')}"
        )

    def test_magfira_user_id(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Magfira] spent 50k on groceries via cash",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "magfira", (
            f"Expected user_id='magfira'. Got: {args.get('user_id')}"
        )

    def test_unknown_user_auto_created(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Ahmad] spent 50k on coffee via dana",
            fake_responses={"get_metadata": META_RESPONSE, "list_accounts": "[]", "create_transaction": TRANSACTION_RESPONSE},
        )
        text = resp.text.lower()
        assert "user_id" not in text, "Bot should not ask for user_id"
        args = resp.find_tool_call("create_transaction")
        if args:
            assert args.get("user_id") == "ahmad"

    def test_never_asks_for_user_id(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] bought coffee 35k via gopay",
            fake_responses=STANDARD_FAKES,
        )
        text = resp.text.lower()
        assert "what is your user" not in text
        assert "what's your user" not in text
        assert "need to know your user" not in text

    def test_alias_firrr_resolves_to_magfira(self, llm, system_prompt):
        """Discord nickname 'firrr' is Magfira — must use user_id='magfira'."""
        resp = ask_multi(
            llm, system_prompt, "[from: firrr] spent 50k on groceries via cash",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "magfira", (
            f"Expected user_id='magfira' for alias 'firrr'. Got: {args.get('user_id')}"
        )
        assert args.get("user_id") != "firrr", "Should NOT use raw display name 'firrr'"

    def test_alias_firrr_gets_magfira_accounts(self, llm, system_prompt):
        """When firrr logs a transaction, bot should query magfira's accounts."""
        resp = ask_multi(
            llm, system_prompt, "[from: firrr] spent 25k on coffee via CBA",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            acct = args.get("from_account_id", "")
            assert "fazrin" not in acct.lower(), (
                f"firrr (Magfira) should not use fazrin's account: {acct}"
            )
            assert acct.lower() in ("cba", "magfira_cba"), (
                f"Expected magfira's CBA, got '{acct}'"
            )

    def test_alias_firrr_uses_sydney_timezone(self, llm, system_prompt):
        """firrr is Magfira — should target Australia/Sydney timezone."""
        resp = ask_multi(
            llm, system_prompt, "[from: firrr] bought lunch 30k via cash at 2pm",
            fake_responses={"get_metadata": META_RESPONSE, "list_accounts": MAGFIRA_ACCOUNTS, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert _has_sydney_tz(args), (
                f"firrr (Magfira) should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{args.get('effective_at', '')}'"
            )

    def test_alias_eifzed_resolves_to_fazrin(self, llm, system_prompt):
        """Discord nickname 'eifzed' is Fazrin — must use user_id='fazrin'."""
        resp = ask_multi(
            llm, system_prompt, "[from: eifzed] spent 50k for gym via jago",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "fazrin", (
            f"Expected user_id='fazrin' for alias 'eifzed'. Got: {args.get('user_id')}"
        )
        assert args.get("user_id") != "eifzed", "Should NOT use raw display name 'eifzed'"


# ──────────────────────────────────────────────────────────────────────────────
# 1b. Sender format resilience — both [from: Name] and [Name] work
# ──────────────────────────────────────────────────────────────────────────────


class TestSenderFormatResilience:
    """Bot handles both OpenClaw's [from: Name] and bare [Name] sender labels."""

    def test_bare_bracket_fazrin(self, llm, system_prompt):
        """Legacy [Name] format should still extract user_id correctly."""
        resp = ask_multi(
            llm, system_prompt, "[Fazrin] spent 50k on parking via cash",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "fazrin", (
            f"Expected user_id='fazrin' from bare [Fazrin]. Got: {args.get('user_id')}"
        )

    def test_bare_bracket_magfira(self, llm, system_prompt):
        """Legacy [Name] format should work for Magfira too."""
        resp = ask_multi(
            llm, system_prompt, "[Magfira] spent 50k on groceries via cash",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "magfira", (
            f"Expected user_id='magfira' from bare [Magfira]. Got: {args.get('user_id')}"
        )

    def test_bare_bracket_alias_firrr(self, llm, system_prompt):
        """Legacy [Name] with alias should still resolve correctly."""
        resp = ask_multi(
            llm, system_prompt, "[firrr] spent 50k on groceries via cash",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "magfira", (
            f"Expected user_id='magfira' for bare [firrr]. Got: {args.get('user_id')}"
        )

    def test_bare_bracket_unknown_user(self, llm, system_prompt):
        """Legacy [Name] format for unknown users should auto-create."""
        resp = ask_multi(
            llm, system_prompt, "[Yusuf] spent 20k on snacks via cash",
            fake_responses={"get_metadata": META_RESPONSE, "list_accounts": "[]", "create_transaction": TRANSACTION_RESPONSE},
        )
        text = resp.text.lower()
        assert "user_id" not in text, "Bot should not ask for user_id"
        args = resp.find_tool_call("create_transaction")
        if args:
            assert args.get("user_id") == "yusuf"

    def test_bare_bracket_magfira_uses_sydney_tz(self, llm, system_prompt):
        """Legacy [Name] format for Magfira should still target Australia/Sydney."""
        resp = ask_multi(
            llm, system_prompt, "[Magfira] bought lunch 30k via cash at 2pm",
            fake_responses={"get_metadata": META_RESPONSE, "list_accounts": MAGFIRA_ACCOUNTS, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert _has_sydney_tz(args), (
                f"Magfira via bare [Magfira] should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{args.get('effective_at', '')}'"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 2. Account ownership — use the correct user's accounts
# ──────────────────────────────────────────────────────────────────────────────


class TestAccountOwnership:
    """Bot uses the transaction sender's own accounts, never another user's."""

    def test_fazrin_gets_own_account(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] spent 100k on groceries via BCA",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        acct = args.get("from_account_id", "")
        assert "magfira" not in acct.lower(), f"Fazrin's txn used magfira's account: {acct}"
        assert acct.lower() in ("bca", "fazrin_bca"), f"Unexpected account: {acct}"

    def test_magfira_gets_own_account(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Magfira] spent 100k on groceries via CBA",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        acct = args.get("from_account_id", "")
        assert "fazrin" not in acct.lower(), f"Magfira's txn used fazrin's account: {acct}"
        assert acct.lower() in ("cba", "magfira_cba"), f"Unexpected account: {acct}"

    def test_magfira_cash_not_fazrin_cash(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Magfira] spent 20k on snacks via cash",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        acct = args.get("from_account_id", "")
        assert "fazrin" not in acct.lower(), f"Magfira's cash txn routed to fazrin: {acct}"

    def test_expense_user_and_account_match(self, llm, system_prompt):
        """Person A's expense must have user_id=A AND from_account_id belonging to A."""
        resp = ask_multi(
            llm, system_prompt, "[from: Magfira] bought groceries for 80k via CBA",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "magfira", (
            f"user_id should be 'magfira', got '{args.get('user_id')}'"
        )
        acct = args.get("from_account_id", "")
        assert "fazrin" not in acct.lower(), (
            f"Magfira's expense deducted from fazrin's account: {acct}"
        )
        assert acct.lower() in ("cba", "magfira_cba"), (
            f"Expected magfira's CBA, got '{acct}'"
        )

    def test_income_goes_to_correct_person(self, llm, system_prompt):
        """Person B's income must credit to person B's account, not person A's."""
        resp = ask_multi(
            llm, system_prompt, "[from: Magfira] salary came in 5000 AUD to CBA",
            fake_responses={
                **MAGFIRA_FAKES,
                "convert_currency": '{"from": "AUD", "to": "IDR", "amount": 5000, "rate": 11951.70, "result": 59758500}',
            },
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "magfira", (
            f"user_id should be 'magfira', got '{args.get('user_id')}'"
        )
        assert args.get("transaction_type") == "income", (
            f"Should be income, got '{args.get('transaction_type')}'"
        )
        to_acct = args.get("to_account_id", "")
        assert "fazrin" not in to_acct.lower(), (
            f"Magfira's salary went to fazrin's account: {to_acct}"
        )
        assert to_acct.lower() in ("cba", "magfira_cba"), (
            f"Expected magfira's CBA for income, got '{to_acct}'"
        )

    def test_fazrin_income_to_own_account(self, llm, system_prompt):
        """Fazrin's income must go to Fazrin's account."""
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] gaji masuk 15jt ke BCA",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "fazrin", (
            f"user_id should be 'fazrin', got '{args.get('user_id')}'"
        )
        assert args.get("transaction_type") == "income"
        to_acct = args.get("to_account_id", "")
        assert "magfira" not in to_acct.lower(), (
            f"Fazrin's salary went to magfira's account: {to_acct}"
        )
        assert to_acct.lower() in ("bca", "fazrin_bca"), (
            f"Expected fazrin's BCA for income, got '{to_acct}'"
        )

    def test_magfira_gopay_deducts_from_her_account(self, llm, system_prompt):
        """Magfira using GoPay should deduct from magfira_GOPAY, not fazrin_GOPAY."""
        resp = ask_multi(
            llm, system_prompt, "[from: Magfira] bought coffee 25k via gopay",
            fake_responses=MAGFIRA_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("user_id") == "magfira", (
            f"user_id should be 'magfira', got '{args.get('user_id')}'"
        )
        acct = args.get("from_account_id", "")
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
            ("[from: Fazrin] spent 300k on groceries via jago", 300000),
            ("[from: Fazrin] spent 50rb on parking via cash", 50000),
            ("[from: Fazrin] gaji masuk 15jt ke BCA", 15000000),
            ("[from: Fazrin] parkir ceban via cash", 10000),
            ("[from: Fazrin] makan goban via jago", 50000),
            ("[from: Fazrin] beli snack cepek via cash", 100000),
            ("[from: Fazrin] beli kopi 2.5k via gopay", 2500),
            ("[from: Fazrin] gaji masuk sejuta ke BCA", 1000000),
            ("[from: Fazrin] beli permen gopek via cash", 500),
            ("[from: Fazrin] beli es seceng via cash", 1000),
            ("[from: Fazrin] beli snack goceng via cash", 5000),
        ],
        ids=["300k", "50rb", "15jt", "ceban", "goban", "cepek", "2.5k", "sejuta", "gopek", "seceng", "goceng"],
    )
    def test_amount_shorthand(self, llm, system_prompt, message, expected_amount):
        resp = ask_multi(llm, system_prompt, message, fake_responses=STANDARD_FAKES)
        all_args = resp.find_all_tool_calls("create_transaction")
        amounts = [a.get("amount") for a in all_args if "amount" in a]
        assert expected_amount in amounts, (
            f"Expected amount {expected_amount} for '{message}'. Got: {amounts}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 4. Intent detection — correct tool for each intent
# ──────────────────────────────────────────────────────────────────────────────


class TestIntentDetection:
    """Bot recognizes user intent and calls the correct MCP tool."""

    def test_expense(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] spent 50k on parking via cash",
            fake_responses=STANDARD_FAKES,
        )
        assert resp.has_tool_call("create_transaction"), "Should call create_transaction"

    def test_income(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] gaji masuk 15jt ke BCA",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("transaction_type") == "income"

    def test_transfer(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] transfer 500k from BCA to Jago",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("transaction_type") == "transfer"
        assert args.get("from_account_id") is not None
        assert args.get("to_account_id") is not None

    def test_check_balance(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[from: Fazrin] what's my balance")
        assert resp.has_tool_call("get_account_balances"), "Should call get_account_balances"

    def test_budget_status(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[from: Fazrin] budget status")
        assert resp.has_tool_call("get_budget_status"), "Should call get_budget_status"

    def test_set_budget(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] set food budget to 3jt for this month",
            fake_responses={**STANDARD_FAKES, "upsert_budget": '{"month": "2026-02", "category_id": "food", "limit_amount": 3000000}'},
        )
        assert resp.has_tool_call("upsert_budget"), "Should call upsert_budget"
        args = resp.find_tool_call("upsert_budget")
        if args:
            assert args.get("limit_amount") == 3000000

    def test_monthly_summary(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[from: Fazrin] how much did I spend this month")
        assert (
            resp.has_tool_call("get_monthly_summary")
            or resp.has_tool_call("list_transactions")
            or resp.has_tool_call("get_metadata")
        ), "Should call a summary or transaction tool"

    def test_void_transaction(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[from: Fazrin] cancel #3")
        assert resp.has_tool_call("void_transaction"), "Should call void_transaction"
        args = resp.find_tool_call("void_transaction")
        assert args is not None
        assert args.get("txn_id") == 3, f"Should void txn_id=3, got {args.get('txn_id')}"

    def test_non_finance_rejected(self, llm, system_prompt):
        resp = ask(llm, system_prompt, "[from: Fazrin] what's the weather today")
        assert len(resp.tool_calls) == 0, "Should not make any tool calls for non-finance messages"
        assert resp.text, "Should reply with text explaining scope"


# ──────────────────────────────────────────────────────────────────────────────
# 5. Category inference — bot picks the right subcategory
# ──────────────────────────────────────────────────────────────────────────────


class TestCategoryInference:
    """Bot infers subcategory from description/merchant when obvious."""

    @pytest.mark.parametrize(
        "message, expected_category",
        [
            ("[from: Fazrin] beli bensin 50k via cash", "fuel"),
            ("[from: Fazrin] parkir ceban via cash", "parking"),
            ("[from: Fazrin] beli kopi 35k di starbucks via gopay", "coffee"),
            ("[from: Fazrin] makan sate 45k via jago", "eating_out"),
            ("[from: Fazrin] belanja di indomaret 80k via cash", "groceries"),
            ("[from: Fazrin] gaji masuk 15jt ke BCA", "salary"),
        ],
        ids=["fuel", "parking", "coffee", "eating_out", "groceries", "salary"],
    )
    def test_category_inferred(self, llm, system_prompt, message, expected_category):
        resp = ask_multi(llm, system_prompt, message, fake_responses=STANDARD_FAKES)
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("category_id") == expected_category, (
            f"Expected category '{expected_category}', got '{args.get('category_id')}'"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 5b. Payment method extraction — bot sets payment_method field
# ──────────────────────────────────────────────────────────────────────────────


class TestPaymentMethodExtraction:
    """Bot correctly sets the payment_method field when mentioned."""

    def test_qris_sets_payment_method(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] beli kopi 35k qris via BCA",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("payment_method") == "qris", (
            f"Expected payment_method='qris', got '{args.get('payment_method')}'"
        )

    def test_cash_sets_payment_method(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] beli bensin 50k cash",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            pm = args.get("payment_method", "")
            if pm:
                assert pm == "cash", (
                    f"Expected payment_method='cash', got '{pm}'"
                )

    def test_debit_sets_payment_method(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] beli groceries 200k debit via BCA",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            pm = args.get("payment_method", "")
            if pm:
                assert pm == "debit", (
                    f"Expected payment_method='debit', got '{pm}'"
                )


# ──────────────────────────────────────────────────────────────────────────────
# 5c. Transfer direction — from/to accounts are not swapped
# ──────────────────────────────────────────────────────────────────────────────


class TestTransferDirection:
    """Bot correctly maps 'from X to Y' to from_account_id and to_account_id."""

    def test_from_bca_to_jago(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] transfer 500k from BCA to Jago",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        assert args.get("transaction_type") == "transfer"
        from_acct = args.get("from_account_id", "").lower()
        to_acct = args.get("to_account_id", "").lower()
        assert "bca" in from_acct, f"from_account should be BCA, got '{from_acct}'"
        assert "jago" in to_acct, f"to_account should be Jago, got '{to_acct}'"

    def test_from_jago_to_bca(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] transfer 1jt from Jago to BCA",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        from_acct = args.get("from_account_id", "").lower()
        to_acct = args.get("to_account_id", "").lower()
        assert "jago" in from_acct, f"from_account should be Jago, got '{from_acct}'"
        assert "bca" in to_acct, f"to_account should be BCA, got '{to_acct}'"

    def test_transfer_ke_phrasing(self, llm, system_prompt):
        """Indonesian 'ke' means 'to': 'transfer 500k ke Jago dari BCA'."""
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] transfer 500k ke Jago dari BCA",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        from_acct = args.get("from_account_id", "").lower()
        to_acct = args.get("to_account_id", "").lower()
        assert "bca" in from_acct, f"'dari BCA' means from BCA, got from='{from_acct}'"
        assert "jago" in to_acct, f"'ke Jago' means to Jago, got to='{to_acct}'"


# ──────────────────────────────────────────────────────────────────────────────
# 5d. Household balance — omit user_id for combined view
# ──────────────────────────────────────────────────────────────────────────────


class TestHouseholdBalance:
    """Bot omits user_id for household-wide queries."""

    def test_household_balance(self, llm, system_prompt):
        """'household balance' or 'semua balance' should omit user_id."""
        resp = ask(llm, system_prompt, "[from: Fazrin] household balances")
        args = resp.find_tool_call("get_account_balances")
        assert args is not None, "Should call get_account_balances"
        assert args.get("user_id") is None, (
            f"Household balance should omit user_id, got '{args.get('user_id')}'"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 6. Time parsing — calls get_metadata first, correct effective_at
# ──────────────────────────────────────────────────────────────────────────────


class TestTimeParsing:
    """Bot calls get_metadata for relative times and produces correct effective_at."""

    def test_relative_time_calls_meta_first(self, llm, system_prompt):
        """When user says 'yesterday', bot must call get_metadata before creating the transaction."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] spent 200k on dinner yesterday 7pm via BCA",
            fake_responses={"get_metadata": META_RESPONSE, "create_transaction": TRANSACTION_RESPONSE},
        )
        names = resp.tool_names
        meta_idx = next((i for i, n in enumerate(names) if n == "get_metadata"), None)
        txn_idx = next((i for i, n in enumerate(names) if n == "create_transaction"), None)

        assert meta_idx is not None, "Should call get_metadata for relative time"
        if txn_idx is not None:
            assert meta_idx < txn_idx, "get_metadata must be called before create_transaction"

    def test_yesterday_effective_at(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] spent 200k on dinner yesterday 7pm via BCA",
            fake_responses={"get_metadata": META_RESPONSE, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "2026-02-24" in ea, f"Yesterday from Feb 25 should be Feb 24, got {ea}"
            assert "19:00" in ea or "T19:" in ea, f"7pm should be 19:00, got {ea}"

    def test_no_time_omits_effective_at(self, llm, system_prompt):
        """When no time is specified, effective_at should be omitted (backend defaults to now)."""
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] spent 50k on parking via cash",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert args.get("effective_at") is None, (
                f"No time specified, but effective_at was set to {args.get('effective_at')}"
            )

    def test_explicit_time_today(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] bought coffee 35k via gopay at 5am",
            fake_responses={"get_metadata": META_RESPONSE, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "05:00" in ea or "T05:" in ea, f"5am should be 05:00, got {ea}"

    def test_two_days_ago(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] bought groceries 300k via jago 2 days ago",
            fake_responses={"get_metadata": META_RESPONSE, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "2026-02-23" in ea, f"2 days before Feb 25 should be Feb 23, got {ea}"


# ──────────────────────────────────────────────────────────────────────────────
# 7. Timezone — Magfira uses Australia/Sydney
# ──────────────────────────────────────────────────────────────────────────────


class TestTimezone:
    """Timezone handling: bot sends timezone name, backend resolves DST/offsets."""

    def test_magfira_sends_sydney_timezone(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] spent 50k on groceries via cash at 3pm",
            fake_responses={"get_metadata": META_RESPONSE, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert _has_sydney_tz(args), (
                f"Magfira should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{args.get('effective_at', '')}'"
            )
            ea = args.get("effective_at", "")
            if ea:
                assert "15:00" in ea or "T15:" in ea, (
                    f"3pm should be 15:00 local, got {ea}"
                )

    def test_magfira_aest_sends_same_timezone(self, llm, system_prompt):
        """In Jul (AEST period), Magfira still targets Australia/Sydney — backend handles DST."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] spent 50k on groceries via cash at 3pm",
            fake_responses={"get_metadata": META_RESPONSE_AEST, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert _has_sydney_tz(args), (
                f"Magfira should target Australia/Sydney in Jul too. Got tz='{args.get('timezone', '')}', ea='{args.get('effective_at', '')}'"
            )

    def test_fazrin_sends_jakarta_timezone(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] bought coffee 15k via cash at 9am",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "09:00" in ea or "T09:" in ea, (
                f"9am should be 09:00 local, got {ea}"
            )
            assert _has_jakarta_tz(args), (
                f"Fazrin should target Asia/Jakarta. Got tz='{args.get('timezone', '')}'"
            )

    def test_magfira_yesterday_sends_timezone(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] bought groceries 30k via cash yesterday 2pm",
            fake_responses={
                "get_metadata": META_RESPONSE,
                "list_accounts": MAGFIRA_ACCOUNTS,
                "create_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert _has_sydney_tz(args), (
                f"Magfira should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{args.get('effective_at', '')}'"
            )
            ea = args.get("effective_at", "")
            if ea:
                assert "2026-02-24" in ea, (
                    f"Yesterday from Feb 25 should be Feb 24, got {ea}"
                )
                assert "14:00" in ea or "T14:" in ea, (
                    f"2pm should be 14:00, got {ea}"
                )

    def test_unknown_user_omits_or_defaults_timezone(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Budi] spent 25k on parking via cash at 8am",
            fake_responses={"get_metadata": META_RESPONSE, "create_transaction": TRANSACTION_RESPONSE},
        )
        args = resp.find_tool_call("create_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "08:00" in ea or "T08:" in ea, (
                f"8am should be 08:00 local, got {ea}"
            )
            assert _has_jakarta_tz(args), (
                f"Unknown user should default to Jakarta. Got tz='{args.get('timezone', '')}'"
            )

    def test_revision_with_utc_response(self, llm, system_prompt):
        """Revision for Magfira should send local time 18:00 targeting Sydney."""
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
            "[from: Magfira] fix #5 should be 6pm",
            fake_responses={
                "get_metadata": META_RESPONSE,
                "get_transaction": utc_txn,
                "correct_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("correct_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "18:00" in ea or "T18:" in ea, (
                f"6pm should be 18:00 local, got {ea}"
            )
            assert _has_sydney_tz(args), (
                f"Magfira revision should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{ea}'"
            )

    def test_fazrin_unaffected_by_aest_period(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] bought coffee 15k via cash at 9am",
            fake_responses={
                "get_metadata": META_RESPONSE_AEST,
                "list_accounts": FAZRIN_ACCOUNTS,
                "create_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("create_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "09:00" in ea or "T09:" in ea, (
                f"9am should be 09:00 local, got {ea}"
            )
            assert _has_jakarta_tz(args), (
                f"Fazrin should use Jakarta regardless of season. Got tz='{args.get('timezone', '')}'"
            )

    def test_magfira_yesterday_aest_sends_timezone(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] bought groceries 30k via cash yesterday 2pm",
            fake_responses={
                "get_metadata": META_RESPONSE_AEST,
                "list_accounts": MAGFIRA_ACCOUNTS,
                "create_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert _has_sydney_tz(args), (
                f"Magfira should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{args.get('effective_at', '')}'"
            )
            ea = args.get("effective_at", "")
            if ea:
                assert "2026-07-14" in ea, (
                    f"Yesterday from Jul 15 should be Jul 14, got {ea}"
                )

    def test_magfira_revision_aest_sends_timezone(self, llm, system_prompt):
        utc_txn = '''{
            "id": 8, "user_id": "magfira", "transaction_type": "expense",
            "amount": 50000, "category_id": "groceries",
            "from_account_id": "magfira_CASH", "to_account_id": null,
            "description": "groceries", "merchant": null,
            "payment_method": null, "effective_at": "2026-07-15T04:00:00+00:00",
            "metadata": {}, "status": "posted"
        }'''
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] fix #8 should be 3pm",
            fake_responses={
                "get_metadata": META_RESPONSE_AEST,
                "get_transaction": utc_txn,
                "correct_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("correct_transaction")
        if args and args.get("effective_at"):
            ea = args["effective_at"]
            assert "15:00" in ea or "T15:" in ea, (
                f"3pm should be 15:00 local, got {ea}"
            )
            assert _has_sydney_tz(args), (
                f"Magfira revision should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{ea}'"
            )

    def test_alias_firrr_sends_sydney_timezone(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: firrr] bought lunch 30k via cash at 2pm",
            fake_responses={
                "get_metadata": META_RESPONSE_AEST,
                "list_accounts": MAGFIRA_ACCOUNTS,
                "create_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert _has_sydney_tz(args), (
                f"firrr (Magfira) should target Australia/Sydney. Got tz='{args.get('timezone', '')}', ea='{args.get('effective_at', '')}'"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 8. Foreign currency conversion — calls convert_currency, uses result
# ──────────────────────────────────────────────────────────────────────────────


class TestCurrencyConversion:
    """Bot calls convert_currency for foreign currencies and uses the result directly."""

    def test_aud_calls_convert(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] bought lunch for 25 AUD via CBA",
            fake_responses={
                "convert_currency": CONVERT_AUD_25,
                "create_transaction": TRANSACTION_RESPONSE,
                "get_metadata": META_RESPONSE,
            },
        )
        assert resp.has_tool_call("convert_currency"), "Should call convert_currency for AUD"

    def test_convert_uses_result_not_manual_calc(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] bought lunch for 25 AUD via CBA",
            fake_responses={
                "convert_currency": CONVERT_AUD_25,
                "create_transaction": TRANSACTION_RESPONSE,
                "get_metadata": META_RESPONSE,
            },
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            assert args.get("amount") == 298792, (
                f"Should use convert result 298792, got {args.get('amount')}"
            )

    def test_convert_stores_original_in_metadata(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] bought lunch for 25 AUD via CBA",
            fake_responses={
                "convert_currency": CONVERT_AUD_25,
                "create_transaction": TRANSACTION_RESPONSE,
                "get_metadata": META_RESPONSE,
            },
        )
        args = resp.find_tool_call("create_transaction")
        if args:
            meta = args.get("metadata", {})
            assert meta.get("original_amount") == 25 or meta.get("original_amount") == 25.0
            assert meta.get("original_currency") == "AUD"

    def test_budget_in_foreign_currency(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Magfira] set food budget to 788 AUD",
            fake_responses={
                "convert_currency": CONVERT_AUD_788,
                "upsert_budget": '{"month": "2026-02", "category_id": "food", "limit_amount": 9417938}',
                "get_metadata": META_RESPONSE,
            },
        )
        assert resp.has_tool_call("convert_currency"), "Should convert AUD to IDR first"
        args = resp.find_tool_call("upsert_budget")
        if args:
            assert args.get("limit_amount") == 9417938, (
                f"Budget should use converted amount 9417938, got {args.get('limit_amount')}"
            )

    def test_small_decimal_aud_calls_convert(self, llm, system_prompt):
        """Small decimal AUD amounts (e.g. 6.39) should use convert_currency, not manual math."""
        convert_639 = '{"from": "AUD", "to": "IDR", "amount": 6.39, "rate": 11926.22, "result": 76209}'
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: firrr] spent aud 6.39 on tempe via jago",
            fake_responses={
                "convert_currency": convert_639,
                "create_transaction": TRANSACTION_RESPONSE,
                "get_metadata": META_RESPONSE,
                "list_accounts": MAGFIRA_ACCOUNTS,
            },
        )
        assert resp.has_tool_call("convert_currency"), "Should call convert_currency for AUD"
        args = resp.find_tool_call("create_transaction")
        if args:
            assert args.get("amount") == 76209, (
                f"Should use convert result 76209, got {args.get('amount')}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 8b. Multi-item messages — one transaction per item
# ──────────────────────────────────────────────────────────────────────────────


class TestMultiItem:
    """Bot creates one transaction per item when user lists multiple purchases."""

    def test_multi_item_creates_multiple_transactions(self, llm, system_prompt):
        """Two items in one message should produce two create_transaction calls."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] beli bensin 50k dan parkir ceban via cash",
            fake_responses=STANDARD_FAKES,
        )
        create_calls = resp.find_all_tool_calls("create_transaction")
        assert len(create_calls) >= 2, (
            f"Expected at least 2 create_transaction calls for 2 items. Got {len(create_calls)}: {create_calls}"
        )

    def test_multi_item_aud_converts_each(self, llm, system_prompt):
        """Multiple AUD items should each go through convert_currency."""
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: firrr] spent aud 6.39 for tempe and aud 2.69 for rice flour, from jago",
            fake_responses={
                "convert_currency": '{"from":"AUD","to":"IDR","amount":6.39,"rate":11926.22,"result":76209}',
                "create_transaction": TRANSACTION_RESPONSE,
                "get_metadata": META_RESPONSE,
                "list_accounts": MAGFIRA_ACCOUNTS,
            },
        )
        convert_calls = resp.find_all_tool_calls("convert_currency")
        assert len(convert_calls) >= 1, "Should call convert_currency at least once for AUD items"
        create_calls = resp.find_all_tool_calls("create_transaction")
        assert len(create_calls) >= 2, (
            f"Expected at least 2 create_transaction calls. Got {len(create_calls)}"
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
            "[from: Fazrin] fix #1 should be 350k",
            fake_responses={
                "get_transaction": GET_TXN_1_RESPONSE,
                "correct_transaction": TRANSACTION_RESPONSE,
            },
        )
        names = resp.tool_names
        get_idx = next((i for i, n in enumerate(names) if n == "get_transaction"), None)
        correct_idx = next((i for i, n in enumerate(names) if n == "correct_transaction"), None)

        assert get_idx is not None, "Should call get_transaction first"
        if correct_idx is not None:
            assert get_idx < correct_idx, "get_transaction must come before correct_transaction"

    def test_revision_changes_only_amount(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] fix #1 should be 350k",
            fake_responses={
                "get_transaction": GET_TXN_1_RESPONSE,
                "correct_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("correct_transaction")
        if args:
            assert args.get("amount") == 350000, f"Amount should be 350000, got {args.get('amount')}"
            assert args.get("category_id") == "groceries", "Category should carry over from original"
            assert args.get("from_account_id") is not None, "Account should carry over from original"

    def test_revision_does_not_ask_unnecessary_questions(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] fix #1 should be 350k",
            fake_responses={
                "get_transaction": GET_TXN_1_RESPONSE,
                "correct_transaction": TRANSACTION_RESPONSE,
            },
        )
        text = resp.text.lower()
        assert "category" not in text or "groceries" in text, "Should not ask about category"
        assert "which account" not in text, "Should not ask about account"

    def test_revision_time_only(self, llm, system_prompt):
        resp = ask_multi(
            llm,
            system_prompt,
            "[from: Fazrin] change #1 to yesterday 5pm",
            fake_responses={
                "get_transaction": GET_TXN_1_RESPONSE,
                "get_metadata": META_RESPONSE,
                "correct_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("correct_transaction")
        if args:
            assert args.get("amount") == 300000, "Amount should stay 300000"
            assert args.get("category_id") == "groceries", "Category should stay groceries"
            ea = args.get("effective_at", "")
            assert "2026-02-24" in ea, f"Yesterday should be Feb 24, got {ea}"


# ──────────────────────────────────────────────────────────────────────────────
# 10. Clarification — asks with options, only when truly needed
# ──────────────────────────────────────────────────────────────────────────────


class TestClarification:
    """Bot asks specific clarification questions when required fields are missing."""

    def test_asks_account_when_missing(self, llm, system_prompt):
        """Fazrin has multiple accounts — bot should ask which one."""
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] beli bensin 50k",
            fake_responses=STANDARD_FAKES, max_turns=2,
        )
        text = resp.text.lower()
        has_create = resp.has_tool_call("create_transaction")
        if not has_create and text:
            has_options = any(kw in text for kw in ["bca", "jago", "cash", "gopay", "ovo"])
            assert has_options, (
                f"Should offer account options when from_account is missing. Got: {resp.text}"
            )

    def test_qris_still_needs_account(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] beli kopi 35k qris",
            fake_responses=STANDARD_FAKES, max_turns=2,
        )
        text = resp.text.lower()
        has_create = resp.has_tool_call("create_transaction")
        if not has_create and text:
            assert "qris" in text or any(
                kw in text for kw in ["bca", "jago", "gopay", "ovo"]
            ), "Should ask which account the QRIS was charged to"

    def test_fully_specified_no_clarification(self, llm, system_prompt):
        """When all fields are present, bot should not ask any questions."""
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] transfer 500k from BCA to Jago",
            fake_responses=STANDARD_FAKES,
        )
        assert resp.has_tool_call("create_transaction"), (
            "All fields specified — should create transaction directly, not ask questions"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 11. Safety — things the bot must NEVER do
# ──────────────────────────────────────────────────────────────────────────────


class TestSafety:
    """Bot must never do dangerous things."""

    def test_never_calls_unknown_tools(self, llm, system_prompt):
        """Bot should only use the defined MCP tools."""
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] what's my balance",
            fake_responses=STANDARD_FAKES,
        )
        known_tools = {
            "create_transaction", "list_transactions", "get_transaction",
            "void_transaction", "correct_transaction", "list_accounts",
            "get_account_balances", "create_account", "adjust_account_balance",
            "upsert_budget", "list_budgets", "get_budget_status",
            "get_budget_history", "get_monthly_summary", "get_metadata",
            "convert_currency", "health_check",
        }
        for name in resp.tool_names:
            assert name in known_tools, f"Unknown tool called: {name}"


# ──────────────────────────────────────────────────────────────────────────────
# 11b. Transaction IDs — must be integers, never UUIDs
# ──────────────────────────────────────────────────────────────────────────────


class TestTransactionIds:
    """Transaction IDs are auto-incrementing integers (1, 2, 3...), not UUIDs."""

    def test_void_uses_integer_id(self, llm, system_prompt):
        """'cancel #3' should call void_transaction with txn_id=3."""
        resp = ask(llm, system_prompt, "[from: Fazrin] cancel #3")
        args = resp.find_tool_call("void_transaction")
        assert args is not None, "Should call void_transaction"
        assert args.get("txn_id") == 3, (
            f"Should use integer ID 3, got {args.get('txn_id')}"
        )

    def test_get_transaction_uses_integer_id(self, llm, system_prompt):
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] show me transaction #7",
            fake_responses={
                "get_transaction": GET_TXN_1_RESPONSE,
                "get_metadata": META_RESPONSE,
            },
        )
        args = resp.find_tool_call("get_transaction")
        assert args is not None, "Should call get_transaction"
        assert args.get("txn_id") == 7, (
            f"Should use integer ID 7, got {args.get('txn_id')}"
        )

    def test_correct_uses_integer_id(self, llm, system_prompt):
        """'fix #1' should call correct_transaction with txn_id=1."""
        resp = ask_multi(
            llm, system_prompt, "[from: Fazrin] fix #1 should be 350k",
            fake_responses={
                "get_transaction": GET_TXN_1_RESPONSE,
                "correct_transaction": TRANSACTION_RESPONSE,
            },
        )
        args = resp.find_tool_call("correct_transaction")
        assert args is not None, "Should call correct_transaction"
        assert args.get("txn_id") == 1, (
            f"Should use integer ID 1, got {args.get('txn_id')}"
        )

    def test_void_id_from_natural_language(self, llm, system_prompt):
        """'cancel transaction number 12' should use txn_id=12."""
        resp = ask(llm, system_prompt, "[from: Fazrin] cancel transaction number 12")
        args = resp.find_tool_call("void_transaction")
        assert args is not None, "Should call void_transaction"
        assert args.get("txn_id") == 12, (
            f"Should extract integer ID 12 from message. Got: {args.get('txn_id')}"
        )
        text = resp.text.lower()
        assert "uuid" not in text, "Bot should not mention or ask for UUIDs"


# ──────────────────────────────────────────────────────────────────────────────
# 12. Metadata — raw_text stored for audit
# ──────────────────────────────────────────────────────────────────────────────


class TestMetadata:
    """Bot includes metadata.raw_text in every transaction."""

    def test_raw_text_included(self, llm, system_prompt):
        msg = "spent 300k on groceries at alfamart via jago"
        resp = ask_multi(
            llm, system_prompt, f"[from: Fazrin] {msg}",
            fake_responses=STANDARD_FAKES,
        )
        args = resp.find_tool_call("create_transaction")
        assert args is not None, "Should call create_transaction"
        meta = args.get("metadata", {})
        assert "raw_text" in meta, "metadata.raw_text should be included"
        assert msg in meta["raw_text"] or "groceries" in meta.get("raw_text", ""), (
            "raw_text should contain the original message"
        )
