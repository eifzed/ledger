---
name: finance-api
description: Household finance API — log transactions, manage budgets, check balances, and get summaries.
user-invocable: false
metadata: {"openclaw":{"requires":{"env":["FINANCE_API_KEY"]},"primaryEnv":"FINANCE_API_KEY"}}
---

# Finance API

Household finance backend on `http://127.0.0.1:8000`. Use the wrapper script for all calls:

```bash
{baseDir}/api.sh <METHOD> <PATH> [JSON_BODY]
```

The script handles base URL, `X-API-Key` auth, and `Content-Type` automatically.

---

## Transactions

### Create transaction

```bash
{baseDir}/api.sh POST /v1/transactions '{
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

**Response** includes: `transaction`, `balances`, `budget_status`, `warnings`.

### List transactions

```bash
{baseDir}/api.sh GET "/v1/transactions?month=2026-02&user_id=fazrin&limit=10"
```

Query params: `month` (YYYY-MM), `category_id`, `user_id`, `account_id`, `search`, `limit` (1-200, default 50), `offset` (default 0).

### Get single transaction

```bash
{baseDir}/api.sh GET /v1/transactions/TRANSACTION_UUID
```

### Void transaction

```bash
{baseDir}/api.sh POST /v1/transactions/TRANSACTION_UUID/void
```

Irreversibly sets status to "voided" and reverses balance effects.

### Correct transaction

```bash
{baseDir}/api.sh POST /v1/transactions/TRANSACTION_UUID/correct '{
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
{baseDir}/api.sh GET "/v1/budgets/status?month=2026-02"
```

Returns usage, remaining, percent, and warnings per category. `month` defaults to current month if omitted.

### List budgets

```bash
{baseDir}/api.sh GET "/v1/budgets?month=2026-02"
```

### Upsert budget

```bash
{baseDir}/api.sh PUT /v1/budgets/2026-02/food '{"limit_amount": 3000000}'
```

Path: `/v1/budgets/{month}/{category_id}`. Only parent categories allowed. Optional `scope_user_id` (null = household).

### Budget history

```bash
{baseDir}/api.sh GET "/v1/budgets/history?month=2026-02&limit=50"
```

---

## Accounts

### Get balances

```bash
{baseDir}/api.sh GET /v1/accounts/balances
```

### List accounts

```bash
{baseDir}/api.sh GET /v1/accounts
```

### Create account

```bash
{baseDir}/api.sh POST /v1/accounts '{"id": "DANA", "display_name": "Dana", "type": "ewallet"}'
```

Types: `bank`, `cash`, `ewallet`, `credit_card`, `other`.

### Adjust balance

```bash
{baseDir}/api.sh POST /v1/accounts/BCA/adjust '{"amount": 5000000, "user_id": "fazrin", "note": "Initial balance"}'
```

Positive = credit, negative = debit.

---

## Summary & Metadata

### Monthly summary

```bash
{baseDir}/api.sh GET "/v1/summary/monthly?month=2026-02"
```

Returns: `total_expenses`, `total_income`, `net`, `by_category`, `by_user`, `daily_totals`, `top_merchants`, `budget_status`, `warnings`.

### Get metadata

```bash
{baseDir}/api.sh GET /v1/meta
```

Returns all categories, accounts, users, payment methods, transaction types, and server time. Call this to discover valid IDs.

### Health check

```bash
{baseDir}/api.sh GET /health
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
