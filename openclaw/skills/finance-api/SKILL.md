---
name: finance-api
description: Household finance API — log transactions, manage budgets, check balances, and get summaries.
user-invocable: false
metadata: {"openclaw":{"requires":{"env":["FINANCE_API_KEY"]},"primaryEnv":"FINANCE_API_KEY"}}
---

# Finance API

Household finance backend. All calls go through `exec` with `curl`.

**Base URL:** `http://127.0.0.1:8000`

Every request needs the API key header. Use this pattern for ALL calls:

```bash
curl -s -X <METHOD> "http://127.0.0.1:8000<PATH>" -H "X-API-Key: $FINANCE_API_KEY" [-H "Content-Type: application/json" -d '<JSON_BODY>']
```

**CRITICAL:** Always use `exec` with `curl` as shown above. Never use `web_fetch` — it cannot send the required `X-API-Key` header.

---

## Transactions

### Create transaction

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/transactions" -H "X-API-Key: $FINANCE_API_KEY" -H "Content-Type: application/json" -d '{
  "user_id": "fazrin",
  "transaction_type": "expense",
  "amount": 65000,
  "category_id": "groceries",
  "from_account_id": "BCA",
  "description": "detergent",
  "merchant": "Indomaret",
  "payment_method": "qris",
  "metadata": {"raw_text": "beli detergent 65k qris bca"}
}'
```

**Required fields by type:**
- **expense**: `user_id`, `transaction_type`, `amount`, `category_id`, `from_account_id` (`to_account_id` must be null)
- **income**: `user_id`, `transaction_type`, `amount`, `to_account_id`
- **transfer**: `user_id`, `transaction_type`, `amount`, `from_account_id`, `to_account_id`
- **adjustment**: `user_id`, `transaction_type`, `amount`

**Optional fields:** `currency` (default IDR), `description`, `merchant`, `payment_method` (cash|qris|debit|credit|bank_transfer|ewallet|other), `note`, `metadata`, `effective_at` (ISO 8601, defaults to now).

**Response** includes: `transaction` (with integer `id` — always show it as `#id` in receipts), `balances`, `budget_status`, `warnings`.

### List transactions

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/transactions?month=2026-02&user_id=fazrin&limit=10" -H "X-API-Key: $FINANCE_API_KEY"
```

Query params: `month` (YYYY-MM), `category_id`, `user_id`, `account_id`, `search`, `limit` (1-200, default 50), `offset` (default 0).

### Get single transaction

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/transactions/42" -H "X-API-Key: $FINANCE_API_KEY"
```

Transaction IDs are auto-incrementing integers (1, 2, 3, ...).

### Void transaction

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/transactions/42/void" -H "X-API-Key: $FINANCE_API_KEY"
```

Irreversibly sets status to "voided" and reverses balance effects.

### Correct transaction

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/transactions/42/correct" -H "X-API-Key: $FINANCE_API_KEY" -H "Content-Type: application/json" -d '{
  "user_id": "fazrin",
  "transaction_type": "expense",
  "amount": 75000,
  "category_id": "groceries",
  "from_account_id": "BCA"
}'
```

Voids the original and creates a replacement. Body is the same schema as create.

---

## Budgets

### Get budget status

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/budgets/status?month=2026-02" -H "X-API-Key: $FINANCE_API_KEY"
```

Returns usage, remaining, percent, and warnings per category. `month` defaults to current month if omitted.

### List budgets

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/budgets?month=2026-02" -H "X-API-Key: $FINANCE_API_KEY"
```

### Upsert budget

```bash
curl -s -X PUT "http://127.0.0.1:8000/v1/budgets/2026-02/food" -H "X-API-Key: $FINANCE_API_KEY" -H "Content-Type: application/json" -d '{"limit_amount": 3000000}'
```

Path: `/v1/budgets/{month}/{category_id}`. Only parent categories allowed. Optional `scope_user_id` (null = household).

### Budget history

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/budgets/history?month=2026-02&limit=50" -H "X-API-Key: $FINANCE_API_KEY"
```

---

## Accounts

### Get balances

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/accounts/balances" -H "X-API-Key: $FINANCE_API_KEY"
```

### List accounts

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/accounts" -H "X-API-Key: $FINANCE_API_KEY"
```

### Create account

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/accounts" -H "X-API-Key: $FINANCE_API_KEY" -H "Content-Type: application/json" -d '{"id": "DANA", "display_name": "Dana", "type": "ewallet"}'
```

Types: `bank`, `cash`, `ewallet`, `credit_card`, `other`.

### Adjust balance

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/accounts/BCA/adjust" -H "X-API-Key: $FINANCE_API_KEY" -H "Content-Type: application/json" -d '{"amount": 5000000, "user_id": "fazrin", "note": "Initial balance"}'
```

Positive = credit, negative = debit.

---

## Summary & Metadata

### Monthly summary

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/summary/monthly?month=2026-02" -H "X-API-Key: $FINANCE_API_KEY"
```

Returns: `total_expenses`, `total_income`, `net`, `by_category`, `by_user`, `daily_totals`, `top_merchants`, `budget_status`, `warnings`.

### Get metadata

```bash
curl -s -X GET "http://127.0.0.1:8000/v1/meta" -H "X-API-Key: $FINANCE_API_KEY"
```

Returns all categories, accounts, users, payment methods, transaction types, and server time. Call this to discover valid IDs.

### Health check

```bash
curl -s -X GET "http://127.0.0.1:8000/health" -H "X-API-Key: $FINANCE_API_KEY"
```

---

## Error responses

```json
{"error": {"code": "NEEDS_CLARIFICATION", "message": "...", "details": [{"field": "from_account_id", "question": "Which account did you pay from?"}]}}
```

- `NEEDS_CLARIFICATION` → relay the `question` to the user
- `VALIDATION_ERROR` → fix the request
- `NOT_FOUND` → resource doesn't exist
- `DUPLICATE` → resource already exists

Never show raw JSON errors to users.
