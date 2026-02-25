---
name: finance-api
description: Household finance API — log transactions, manage budgets, check balances, and get summaries.
metadata: {"openclaw":{"requires":{"env":["FINANCE_API_KEY"]},"primaryEnv":"FINANCE_API_KEY"}}
---

# Finance API

You have access to a household finance backend running at `http://127.0.0.1:8000`. All API calls require the `X-API-Key` header set to `$FINANCE_API_KEY`.

## Tool Definitions

Each JSON file in `{baseDir}/tools/` defines one API tool. Read the relevant file before calling a tool you haven't used this session.

## How to Call

Use `exec` with `curl` to call the API. Always use `-s` (silent) and parse the JSON response.

### POST / PUT (JSON body)

```bash
curl -s -X POST http://127.0.0.1:8000/v1/transactions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $FINANCE_API_KEY" \
  -d '{"user_id":"fazrin","transaction_type":"expense","amount":65000,"category_id":"groceries","from_account_id":"BCA","description":"detergent","payment_method":"qris","metadata":{"raw_text":"beli detergent 65k qris bca"}}'
```

### GET (query params)

```bash
curl -s "http://127.0.0.1:8000/v1/budgets/status?month=2026-02" \
  -H "X-API-Key: $FINANCE_API_KEY"
```

### Path parameters

Replace `{param}` placeholders in the URL:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/transactions/SOME-UUID/void \
  -H "X-API-Key: $FINANCE_API_KEY"
```

## Available Tools

| Tool | Method | Endpoint |
|---|---|---|
| `create_transaction` | POST | `/v1/transactions` |
| `list_transactions` | GET | `/v1/transactions` |
| `get_transaction` | GET | `/v1/transactions/{txn_id}` |
| `void_transaction` | POST | `/v1/transactions/{txn_id}/void` |
| `correct_transaction` | POST | `/v1/transactions/{txn_id}/correct` |
| `get_metadata` | GET | `/v1/meta` |
| `upsert_budget` | PUT | `/v1/budgets/{month}/{category_id}` |
| `list_budgets` | GET | `/v1/budgets` |
| `get_budget_status` | GET | `/v1/budgets/status` |
| `get_budget_history` | GET | `/v1/budgets/history` |
| `create_account` | POST | `/v1/accounts` |
| `list_accounts` | GET | `/v1/accounts` |
| `get_account_balances` | GET | `/v1/accounts/balances` |
| `adjust_account_balance` | POST | `/v1/accounts/{account_id}/adjust` |
| `get_monthly_summary` | GET | `/v1/summary/monthly` |
| `health_check` | GET | `/health` |

## Error Handling

The API returns structured errors:

```json
{
  "error": {
    "code": "NEEDS_CLARIFICATION",
    "message": "Missing required fields",
    "details": [{"field": "from_account_id", "question": "Which account did you pay from?"}]
  }
}
```

When you get `NEEDS_CLARIFICATION`, relay the `question` from `details` to the user. When you get `VALIDATION_ERROR`, fix the request. Don't show raw JSON to users.
