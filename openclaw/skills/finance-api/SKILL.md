---
name: finance-api
description: Household finance API — log transactions, manage budgets, check balances, and get summaries.
user-invocable: false
metadata: {"openclaw":{"requires":{"env":["FINANCE_API_KEY"]},"primaryEnv":"FINANCE_API_KEY","mcp":true}}
---

# Finance API — MCP Tools

All tools are self-documented via their MCP schemas (parameter names, types, descriptions, and required fields). Call them directly with typed arguments.

## Domain Rules

- **Account IDs** are per-user (e.g. `fazrin_BCA`). Send just the display name (e.g. `"BCA"`) — the backend resolves it to the user's own account.
- **Budgets** can only target **parent** categories (e.g. `food`, not `groceries`).
- **`effective_at`** must always be paired with **`timezone`** (IANA name). The backend handles UTC conversion and DST.
- **`convert_currency`**: use the `result` field directly — never calculate conversions manually.
- **`correct_transaction`**: always fetch the original first, copy all fields, override only what changed.

## Error Codes

| Code | Action |
|---|---|
| `NEEDS_CLARIFICATION` | Relay the `question` to the user with options |
| `VALIDATION_ERROR` | Fix the request and retry once |
| `NOT_FOUND` | Resource doesn't exist |
| `DUPLICATE` | Resource already exists |
