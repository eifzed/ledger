---
name: finance-api
description: Household finance API — log transactions, manage budgets, check balances, and get summaries.
user-invocable: false
metadata: {"openclaw":{"requires":{"env":["FINANCE_API_KEY"]},"primaryEnv":"FINANCE_API_KEY"}}
---

# Finance API — CLI Tools

Call tools via `exec`. Pass arguments as a JSON object:

```
exec: ledger <tool_name> '<json_args>'
```

Examples:
- `exec: ledger health_check`
- `exec: ledger get_account_balances '{"user_id":"fazrin"}'`
- `exec: ledger create_transaction '{"user_id":"fazrin","transaction_type":"expense","amount":50000,"category_id":"fuel","from_account_id":"Jago"}'`

The tool prints JSON to stdout. Parse the result before replying.

Tool parameters are defined in the `tools/` directory (names, types, descriptions, required fields).

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
