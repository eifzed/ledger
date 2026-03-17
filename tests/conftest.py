"""Prompt regression test infrastructure.

Loads the same prompt files OpenClaw uses, sends test messages to an LLM,
and provides helpers to inspect the structured tool calls the bot produces.

With the MCP upgrade, the bot calls typed tools (create_transaction,
get_account_balances, etc.) instead of generating raw curl commands.
Tests assert on tool call names and arguments directly.

Requirements:
    pip install openai pytest python-dotenv

Configuration via .env in project root:
    OPENAI_API_KEY   — required
    TEST_MODEL       — model to use (default: gpt-4o-mini)
    OPENAI_BASE_URL  — override for compatible providers

Logs:
    Test results are written to tests/results/<timestamp>.log after each run.
    The log shows expected vs actual output and PASS/FAIL for every test.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "tests" / "results"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PROMPT_DIR = ROOT / "openclaw" / "prompt"
SKILL_PATH = ROOT / "openclaw" / "skills" / "finance-api" / "SKILL.md"

# ---------------------------------------------------------------------------
# Tool definitions — mirror the MCP server's tools as OpenAI function-calling
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_transaction",
            "description": "Create a financial transaction (expense, income, transfer, or adjustment).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "transaction_type": {"type": "string", "enum": ["expense", "income", "transfer", "adjustment"]},
                    "amount": {"type": "number"},
                    "category_id": {"type": "string"},
                    "from_account_id": {"type": "string"},
                    "to_account_id": {"type": "string"},
                    "description": {"type": "string"},
                    "merchant": {"type": "string"},
                    "payment_method": {"type": "string", "enum": ["cash", "qris", "debit", "credit", "bank_transfer", "ewallet", "other"]},
                    "effective_at": {"type": "string", "description": "ISO 8601 naive local time"},
                    "timezone": {"type": "string", "description": "IANA timezone name"},
                    "note": {"type": "string"},
                    "metadata": {"type": "object"},
                    "currency": {"type": "string"},
                },
                "required": ["user_id", "transaction_type", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "List transactions with optional filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string"},
                    "user_id": {"type": "string"},
                    "category_id": {"type": "string"},
                    "account_id": {"type": "string"},
                    "search": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transaction",
            "description": "Get a single transaction by integer ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "txn_id": {"type": "integer"},
                },
                "required": ["txn_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "void_transaction",
            "description": "Void (cancel) a transaction by integer ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "txn_id": {"type": "integer"},
                },
                "required": ["txn_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "correct_transaction",
            "description": "Correct a transaction: voids original and creates replacement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "txn_id": {"type": "integer"},
                    "user_id": {"type": "string"},
                    "transaction_type": {"type": "string", "enum": ["expense", "income", "transfer", "adjustment"]},
                    "amount": {"type": "number"},
                    "category_id": {"type": "string"},
                    "from_account_id": {"type": "string"},
                    "to_account_id": {"type": "string"},
                    "description": {"type": "string"},
                    "merchant": {"type": "string"},
                    "payment_method": {"type": "string"},
                    "effective_at": {"type": "string"},
                    "timezone": {"type": "string"},
                    "note": {"type": "string"},
                    "metadata": {"type": "object"},
                    "currency": {"type": "string"},
                },
                "required": ["txn_id", "user_id", "transaction_type", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_accounts",
            "description": "List accounts, optionally filtered by user_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_balances",
            "description": "Get current balance for each active account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_account",
            "description": "Create a new account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "display_name": {"type": "string"},
                    "type": {"type": "string", "enum": ["bank", "cash", "ewallet", "credit_card", "other"]},
                    "owner_id": {"type": "string"},
                    "currency": {"type": "string"},
                },
                "required": ["id", "display_name", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_account_balance",
            "description": "Adjust an account's balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "user_id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["account_id", "amount", "user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upsert_budget",
            "description": "Set or update a budget for a parent category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string"},
                    "category_id": {"type": "string"},
                    "limit_amount": {"type": "integer"},
                    "scope_user_id": {"type": "string"},
                },
                "required": ["month", "category_id", "limit_amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_budgets",
            "description": "List all budgets for a month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string"},
                },
                "required": ["month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_status",
            "description": "Get budget usage, remaining, percent, and warnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_history",
            "description": "Get budget change history for a month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_summary",
            "description": "Get spending summary for a month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string"},
                    "user_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metadata",
            "description": "Get categories, accounts, users, payment methods, transaction types, and server time.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_currency",
            "description": "Convert a foreign currency amount to IDR using live exchange rates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "from_currency": {"type": "string"},
                    "to_currency": {"type": "string"},
                },
                "required": ["amount", "from_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_check",
            "description": "Check if the backend is operational.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Test result logging
# ---------------------------------------------------------------------------

_log_entries: list[dict] = []
_current_response: dict = {}


def _record_response(input_message: str, resp: "BotResponse") -> None:
    """Store the latest ask/ask_multi call for the current test."""
    _current_response["input"] = input_message
    _current_response["text"] = resp.content
    _current_response["tool_calls"] = resp.tool_calls


@pytest.fixture(autouse=True)
def _capture_test(request):
    """Auto-capture test name and clear response state before each test."""
    _current_response.clear()
    yield


def pytest_runtest_makereport(item, call):
    """Pytest hook: capture PASS/FAIL and assertion details after each test."""
    if call.when != "call":
        return

    entry = {
        "test": item.nodeid,
        "result": "PASS" if not call.excinfo else "FAIL",
        "input": _current_response.get("input", ""),
        "output": {
            "text": _current_response.get("text", ""),
            "tool_calls": _current_response.get("tool_calls", []),
        },
        "assertion_error": "",
    }

    if call.excinfo:
        entry["assertion_error"] = str(call.excinfo.value)

    _log_entries.append(entry)


def pytest_sessionfinish(session, exitstatus):
    """Pytest hook: write the full test log after all tests complete."""
    if not _log_entries:
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model = os.environ.get("TEST_MODEL", "gpt-4o-mini")
    log_path = RESULTS_DIR / f"{timestamp}.log"

    passed = sum(1 for e in _log_entries if e["result"] == "PASS")
    failed = sum(1 for e in _log_entries if e["result"] == "FAIL")
    total = len(_log_entries)

    lines: list[str] = []
    lines.append(f"{'=' * 80}")
    lines.append("Ledger Bot — Prompt Regression Test Results")
    lines.append(f"{'=' * 80}")
    lines.append(f"Timestamp : {timestamp}")
    lines.append(f"Model     : {model}")
    lines.append(f"Results   : {passed} passed, {failed} failed, {total} total")
    lines.append(f"{'=' * 80}")
    lines.append("")

    for entry in _log_entries:
        status = entry["result"]
        icon = "✅" if status == "PASS" else "❌"
        lines.append(f"{icon} {status} — {entry['test']}")
        lines.append(f"  Input: {entry['input'] or '(n/a)'}")

        output = entry["output"]
        if output["tool_calls"]:
            lines.append("  Tool calls:")
            for tc in output["tool_calls"]:
                args_short = json.dumps(tc["arguments"], ensure_ascii=False)
                if len(args_short) > 200:
                    args_short = args_short[:200] + "..."
                lines.append(f"    {tc['name']}({args_short})")

        if output["text"]:
            text_short = output["text"][:300]
            if len(output["text"]) > 300:
                text_short += "..."
            lines.append(f"  Bot text: {text_short}")

        if entry["assertion_error"]:
            lines.append(f"  Expected: (see assertion below)")
            lines.append(f"  Error: {entry['assertion_error']}")

        lines.append("")

    lines.append(f"{'=' * 80}")
    lines.append(f"Summary: {passed}/{total} passed")
    if failed:
        lines.append("Failed tests:")
        for entry in _log_entries:
            if entry["result"] == "FAIL":
                lines.append(f"  ❌ {entry['test']}")
    lines.append(f"{'=' * 80}")

    log_path.write_text("\n".join(lines), encoding="utf-8")

    json_path = RESULTS_DIR / f"{timestamp}.json"
    json_path.write_text(
        json.dumps(_log_entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n📋 Test log written to: {log_path}")
    print(f"📋 JSON log written to: {json_path}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _load_system_prompt() -> str:
    """Assemble the system prompt from prompt files + skill, mirroring OpenClaw."""
    parts: list[str] = []
    for name in ["IDENTITY.md", "SOUL.md", "AGENTS.md", "USER.md", "TOOLS.md"]:
        path = PROMPT_DIR / name
        if path.exists():
            parts.append(path.read_text())
    if SKILL_PATH.exists():
        parts.append(SKILL_PATH.read_text())
    return "\n\n---\n\n".join(parts)


@pytest.fixture(scope="session")
def system_prompt() -> str:
    return _load_system_prompt()


@pytest.fixture(scope="session")
def llm():
    """Return an OpenAI client, or skip if not configured."""
    try:
        import openai
    except ImportError:
        pytest.skip("openai package not installed — pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    kwargs: dict = {"api_key": api_key}
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url

    return openai.OpenAI(**kwargs)


# ---------------------------------------------------------------------------
# Bot interaction
# ---------------------------------------------------------------------------


class BotResponse:
    """Parsed response from the LLM, with helpers for assertions."""

    def __init__(self, content: str, tool_calls: list[dict], finish_reason: str):
        self.content = content
        self.tool_calls = tool_calls
        self.finish_reason = finish_reason

    @property
    def text(self) -> str:
        return self.content

    def has_tool_call(self, name: str) -> bool:
        """Check if any tool call matches the given name."""
        return any(tc["name"] == name for tc in self.tool_calls)

    def find_tool_call(self, name: str) -> dict | None:
        """Return the arguments of the first tool call matching name, or None."""
        for tc in self.tool_calls:
            if tc["name"] == name:
                return tc["arguments"]
        return None

    def find_all_tool_calls(self, name: str) -> list[dict]:
        """Return arguments of all tool calls matching name."""
        return [tc["arguments"] for tc in self.tool_calls if tc["name"] == name]

    @property
    def tool_names(self) -> list[str]:
        """Names of all tools called, in order."""
        return [tc["name"] for tc in self.tool_calls]


def ask(client, system_prompt: str, message: str, model: str | None = None) -> BotResponse:
    """Send a single message to the LLM with system prompt + MCP tools.

    Returns a BotResponse with parsed tool calls.
    """
    model = model or os.environ.get("TEST_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        tools=TOOLS,
        temperature=0,
    )

    choice = response.choices[0]
    tool_calls = []

    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            tool_calls.append({"name": tc.function.name, "arguments": args})

    resp = BotResponse(
        content=choice.message.content or "",
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason,
    )
    _record_response(message, resp)
    return resp


def ask_multi(
    client,
    system_prompt: str,
    message: str,
    fake_responses: dict[str, str] | None = None,
    max_turns: int = 5,
    model: str | None = None,
) -> BotResponse:
    """Multi-turn: send message, feed fake tool results, collect all tool calls.

    fake_responses maps a **tool name** to a fake JSON response string.
    For example: {"get_metadata": '{"server_time": "..."}',
                  "convert_currency": '{"result": 298792}'}

    All tool calls across all turns are accumulated into the returned BotResponse.
    """
    model = model or os.environ.get("TEST_MODEL", "gpt-4o-mini")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    all_tool_calls: list[dict] = []
    final_content = ""

    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            temperature=0,
        )

        choice = response.choices[0]
        msg = choice.message
        final_content = msg.content or ""

        if not msg.tool_calls:
            break

        messages.append(msg)

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            all_tool_calls.append({"name": tc.function.name, "arguments": args})

            tool_result = '{"status": "ok"}'
            if fake_responses:
                for tool_name, fake_resp in fake_responses.items():
                    if tool_name == tc.function.name:
                        tool_result = fake_resp
                        break

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })

    resp = BotResponse(
        content=final_content,
        tool_calls=all_tool_calls,
        finish_reason=choice.finish_reason,
    )
    _record_response(message, resp)
    return resp
