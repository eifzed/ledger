"""Prompt regression test infrastructure.

Loads the same prompt files OpenClaw uses, sends test messages to an LLM,
and provides helpers to inspect the curl commands the bot would produce.

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
import re
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

EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "exec",
        "description": "Execute a shell command",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                }
            },
            "required": ["command"],
        },
    },
}


# ---------------------------------------------------------------------------
# Test result logging
# ---------------------------------------------------------------------------

_log_entries: list[dict] = []
_current_response: dict = {}


def _record_response(input_message: str, resp: "BotResponse") -> None:
    """Store the latest ask/ask_multi call for the current test."""
    _current_response["input"] = input_message
    _current_response["text"] = resp.content
    _current_response["curls"] = resp.curls
    _current_response["bodies"] = resp.curl_bodies()
    _current_response["all_commands"] = resp.all_commands


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
            "curls": _current_response.get("curls", []),
            "bodies": _current_response.get("bodies", []),
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
    lines.append(f"Ledger Bot — Prompt Regression Test Results")
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
        if output["curls"]:
            lines.append(f"  Curls:")
            for curl in output["curls"]:
                short = curl[:200] + "..." if len(curl) > 200 else curl
                lines.append(f"    {short}")

        if output["bodies"]:
            lines.append(f"  Bodies:")
            for body in output["bodies"]:
                lines.append(f"    {json.dumps(body, indent=None, ensure_ascii=False)}")

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
        lines.append(f"Failed tests:")
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

    @property
    def curls(self) -> list[str]:
        """All curl commands the bot tried to run via exec."""
        return [tc["command"] for tc in self.tool_calls if "curl" in tc.get("command", "")]

    @property
    def all_commands(self) -> list[str]:
        return [tc["command"] for tc in self.tool_calls]

    def curl_bodies(self) -> list[dict]:
        """Parse JSON bodies from all curl -d '...' commands."""
        bodies = []
        for cmd in self.curls:
            body = parse_curl_body(cmd)
            if body is not None:
                bodies.append(body)
        return bodies

    def has_curl(self, method: str, path: str) -> bool:
        """Check if any curl call uses the given method + URL path."""
        for cmd in self.curls:
            if f"-X {method}" in cmd and path in cmd:
                return True
        return False

    def find_curl(self, method: str, path: str) -> str | None:
        """Return the first curl command matching method + path, or None."""
        for cmd in self.curls:
            if f"-X {method}" in cmd and path in cmd:
                return cmd
        return None

    def find_body(self, method: str, path: str) -> dict | None:
        """Return the parsed JSON body of the first matching curl."""
        cmd = self.find_curl(method, path)
        if cmd:
            return parse_curl_body(cmd)
        return None


def ask(client, system_prompt: str, message: str, model: str | None = None) -> BotResponse:
    """Send a single message to the LLM with system prompt + exec tool.

    Returns a BotResponse with parsed tool calls.
    """
    model = model or os.environ.get("TEST_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        tools=[EXEC_TOOL],
        temperature=0,
    )

    choice = response.choices[0]
    tool_calls = []

    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            tool_calls.append({
                "name": tc.function.name,
                "command": args.get("command", ""),
            })

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

    fake_responses maps a URL path fragment to a fake JSON response string.
    For example: {"/v1/meta": '{"server_time": "..."}', "/v1/convert": '{"result": 298792}'}

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
            tools=[EXEC_TOOL],
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
            command = args.get("command", "")
            all_tool_calls.append({"name": tc.function.name, "command": command})

            tool_result = '{"status": "ok"}'
            if fake_responses:
                for path_fragment, fake_resp in fake_responses.items():
                    if path_fragment in command:
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


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_curl_body(curl_cmd: str) -> dict | None:
    """Extract the JSON body from a curl -d '...' or -d "..." command."""
    for pattern in [
        r"-d\s+'(.*?)'",
        r'-d\s+"(.*?)"',
        r"-d\s+(\{.*\})",
    ]:
        match = re.search(pattern, curl_cmd, re.DOTALL)
        if match:
            raw = match.group(1)
            raw = raw.replace('\\"', '"')
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                continue
    return None


def curl_url_path(curl_cmd: str) -> str | None:
    """Extract the URL path from a curl command."""
    match = re.search(r'"http://[^/]+(\/[^"]*)"', curl_cmd)
    if match:
        return match.group(1)
    return None
