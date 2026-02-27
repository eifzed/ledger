## 0) Goals and Non‑Goals

### Goals
1. **SQLite as the single source of truth** for all financial records.
2. Provide a **stable, tool-friendly HTTP API** for the chat agent to:
   - log transactions
   - manage budgets and rules
   - compute balances and summaries
   - produce warnings and insights
3. Provide a **human dashboard endpoint** (web UI) to view transactions, budgets, and stats.
4. No Google Sheets / Docs dependency.

### Non‑Goals (for MVP)
- Bank account syncing / Open Banking integrations
- Receipt OCR (can be added later)
- Multi-tenant SaaS (this is for a couple)
- Full accounting (double-entry) unless needed later

---

## 1) High-Level Architecture

**Discord** → **OpenClaw (LLM + tool calling)** → **Python Finance API** → **SQLite**  
Dashboard is served by the Python Finance API.

**Principles:**
- The LLM is a **parser + coordinator**, not the accountant.
- The server performs **all calculations** (budgets, balances, summaries).
- All writes are **validated** and **auditable**.
- Prefer **append-only ledger** semantics (corrections are new entries), to preserve history.

---

## 2) Tech Stack (Recommended)

- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (or sqlite3 + Pydantic if preferred)
- Jinja2 templates for dashboard pages (simple) OR a small React/Vite frontend later
- Pydantic models for strict request validation
- Alembic migrations (recommended for schema evolution)

**SQLite settings**
- Enable **WAL mode** for better concurrent reads/writes.
- Use `PRAGMA foreign_keys = ON;`.
- Store DB on local disk (EBS), not network FS.

---

## 3) Data Model

### 3.1 Core Concepts

- **User**: Auto-created from Discord display name on first transaction. Seeded: “fazrin” (Jakarta, UTC+7) and “magfira” (Sydney, UTC+11). Identified by `user_id` and `display_name`.
- **Account**: Per-user accounts (e.g. `fazrin_BCA`, `magfira_CBA`). Each has an `owner_id`. Holds a computed balance.
- **Transaction**: Atomic record of money movement (expense, income, transfer).
- **Budget**: Monthly caps per category (optionally per user).
- **Category**: Fixed list + configurable (Groceries, Fun, Car, Bills, etc.).
- **Merchant / Item** (optional): For better categorization and insights.
- **Category Rules**: Keyword/merchant mappings to assist classification (server-side).

### 3.2 Enumerations

**transaction_type**
- `expense`
- `income`
- `transfer`
- `adjustment` (optional; for reconciliation/starting balances)

**payment_method**
- `cash`
- `qris`
- `debit`
- `credit`
- `bank_transfer`
- `ewallet`
- `other`

**currency**
- `IDR` (default), support multi-currency later if needed.

### 3.3 Suggested SQLite Schema (MVP)

#### users
- id (TEXT, PK) — stable identifier
- display_name (TEXT)
- created_at (DATETIME)

#### accounts
- id (TEXT, PK) — e.g., "fazrin_BCA", "magfira_CBA" (prefixed with owner_id)
- display_name (TEXT)
- type (TEXT) — e.g., "bank", "cash", "ewallet"
- owner_id (TEXT, FK users.id, nullable) — which user owns this account
- currency (TEXT) — default "IDR"
- is_active (INTEGER)
- created_at (DATETIME)

#### categories
- id (TEXT, PK) — e.g., "groceries"
- display_name (TEXT) — e.g., "Groceries"
- parent_id (TEXT, FK nullable) — optional subcategories
- is_active (INTEGER)

#### budgets
- id (INTEGER, PK AUTOINCREMENT)
- month (TEXT) — "YYYY-MM"
- category_id (TEXT, FK categories.id)
- limit_amount (INTEGER) — store in smallest unit (IDR), integer
- scope_user_id (TEXT nullable) — null means household-level
- created_at (DATETIME)
- updated_at (DATETIME)

#### transactions
- id (INTEGER, PK AUTOINCREMENT) — auto-incrementing integer
- created_at (DATETIME) — server time
- effective_at (DATETIME) — when it happened (ISO 8601 with timezone offset; defaults to server now). The Discord bot parses natural language time expressions ("at 5am", "yesterday 3pm", etc.) into this field.
- user_id (TEXT, FK users.id) — who logged it / who did it
- transaction_type (TEXT)
- amount (INTEGER) — positive integer in IDR
- currency (TEXT) — default "IDR"
- category_id (TEXT, FK categories.id nullable) — required for expense; optional for others
- description (TEXT) — raw item/merchant text, e.g., "detergent indomaret"
- merchant (TEXT nullable)
- payment_method (TEXT nullable)
- from_account_id (TEXT FK accounts.id nullable)
- to_account_id (TEXT FK accounts.id nullable)
- external_ref (TEXT nullable) — optional id for import
- note (TEXT nullable)
- status (TEXT) — e.g., "posted" | "voided" (voided by correction)
- correction_of (INTEGER nullable FK transactions.id) — if this is a correction
- metadata_json (TEXT nullable) — JSON string for extra fields

**Rules by type (server validation):**
- expense: require `from_account_id` (where money left), require `category_id`, disallow `to_account_id`.
- income: require `to_account_id`, category optional.
- transfer: require both `from_account_id` and `to_account_id`, category null.
- adjustment: can target one account.

#### category_rules (optional, but recommended)
- id (INTEGER PK)
- rule_type (TEXT) — "keyword" | "merchant"
- pattern (TEXT) — keyword or merchant match
- category_id (TEXT)
- priority (INTEGER) — higher wins
- is_active (INTEGER)

#### monthly_snapshots (optional)
- month (TEXT, PK)
- cached_json (TEXT) — computed aggregates cached
- created_at (DATETIME)

---

## 4) Computation Rules

### 4.1 Balances
Compute balances from transactions + optional initial balance entries.

For each account:
- Start with sum of `adjustment` entries for that account (or a single initial adjustment)
- Apply:
  - expense: subtract amount from `from_account_id`
  - income: add amount to `to_account_id`
  - transfer: subtract from `from_account_id`, add to `to_account_id`
  - voided transactions are ignored
Return current balances per account.

### 4.2 Monthly Spend
For month M (YYYY-MM):
- expenses where `effective_at` in month, status=posted
- group by category, user (optional)
Compute:
- MTD total spend
- category spend
- top merchants/items
- daily trend (optional)

### 4.3 Budget Status + Warnings
For each budget entry (month, category, scope):
- used = sum(expenses in category/scope, month)
- remaining = limit - used
- percent = used / limit
Warnings:
- warn at >= 80% (configurable)
- exceeded at >= 100%
Return warnings in API responses so the chat bot can display them.

---

## 5) HTTP API Spec (Tool-Friendly)

### 5.1 Auth (recommended even for private)
Simplest:
- Single API key in header: `X-API-Key: <secret>`
- Reject if missing/invalid.
- Dashboard can use same key via cookie/session or basic auth for MVP.

### 5.2 Endpoints (MVP)

#### Health
- `GET /health`
  - Returns { "status": "ok" }

#### Metadata
- `GET /v1/meta`
  - Returns categories, accounts, users, payment methods enum, current server time.

#### Transactions
- `POST /v1/transactions`
  - Creates a transaction. Request schema below.
- `GET /v1/transactions`
  - Query params: `month=YYYY-MM`, `category_id`, `user_id`, `account_id`, `limit`, `offset`, `search`
- `GET /v1/transactions/{id}`
- `POST /v1/transactions/{id}/void`
  - Voids a transaction (admin-only), or use correction flow.
- `POST /v1/transactions/{id}/correct`
  - Creates a correction transaction referencing the original.

**POST /v1/transactions request (Pydantic)**
```json
{
  "effective_at": "2026-02-24T10:30:00+07:00",
  "user_id": "fazrin",
  "transaction_type": "expense",
  "amount": 65000,
  "currency": "IDR",
  "category_id": "groceries",
  "description": "detergent indomaret",
  "merchant": "Indomaret",
  "payment_method": "qris",
  "from_account_id": "fazrin_BCA",
  "to_account_id": null,
  "note": "optional",
  "metadata": {
    "raw_text": "beli detergent 65k qris bca at 10.30am"
  }
}
```

`effective_at` accepts ISO 8601 with timezone offset. The Discord bot parses natural language time expressions ("at 5am", "yesterday 3pm", "at 17.30") into this field. If omitted, defaults to server's current time.

Return:
```json
{
  "transaction": { "id": 1, ...normalized fields... },
  "balances": [{ "account_id": "fazrin_BCA", "balance": 12345000 }],
  "budget_status": [
    { "category_id": "groceries", "month": "2026-02", "limit": 3000000, "used": 1200000, "remaining": 1800000, "percent": 0.4, "warning": null }
  ],
  "warnings": [
    { "type": "budget", "severity": "info|warn|error", "message": "Groceries is at 80% of limit" }
  ]
}
```

#### Budgets
- `PUT /v1/budgets/{month}/{category_id}`
  - Body: `{ "limit_amount": 3000000, "scope_user_id": null }`
- `GET /v1/budgets?month=YYYY-MM`
- `GET /v1/budgets/status?month=YYYY-MM`
  - Returns budget usage/remaining + warnings.

#### Accounts
- `POST /v1/accounts` — include `owner_id` to assign to a user
- `GET /v1/accounts?user_id=fazrin` — optional `user_id` filter by owner
- `GET /v1/accounts/balances?user_id=fazrin` — optional `user_id` filter
- `POST /v1/accounts/{id}/adjust`
  - Adds an adjustment transaction (initial balance or reconciliation).

#### Rules (optional for MVP)
- `POST /v1/category-rules`
- `GET /v1/category-rules`
- `DELETE /v1/category-rules/{id}`

#### Summaries / Reports
- `GET /v1/summary/monthly?month=YYYY-MM&user_id=fazrin`
  - Returns totals, by category, by user, by account, top merchants, daily totals. Optional `user_id` filter for per-user view; omit for household totals.

#### Purchase Advice (Phase 2)
- `GET /v1/advice/purchase`
  - Query: `item=RTX%205070`
  - For MVP, can return “not implemented”. Later: call a controlled price service.

---

## 6) Dashboard Spec

### 6.1 Requirements
- Served from the same FastAPI app.
- Minimal authentication (same API key or basic auth).
- Pure server-rendered pages are acceptable for MVP.

### 6.2 Pages (MVP)
1. `/` — Overview
   - current month totals
   - budget usage bars
   - account balances
   - warnings panel

2. `/transactions`
   - table with filters (month, category, user, account, search)
   - pagination
   - ability to click a transaction to view details

3. `/budgets`
   - list budgets for selected month
   - edit budget limits (optional UI; can be API-only initially)

4. `/accounts`
   - list accounts + balances
   - add adjustment (optional)

### 6.3 UX Notes
- Show amounts formatted in IDR with separators.
- Show month selector.
- Show warnings clearly (80% threshold, exceeded).
- Keep it fast and simple; no heavy JS required.

---

## 7) OpenClaw Tool Contracts (what the LLM calls)

OpenClaw should only call a small set of safe tools that map to the API.

### Tools (minimum)
- `log_expense(amount, description, category_id?, payment_method?, account_id?, effective_at?)`
- `log_income(amount, description, account_id, effective_at?)`
- `log_transfer(amount, from_account_id, to_account_id, effective_at?)`
- `get_budget_status(month?)`
- `get_balances()`
- `get_monthly_summary(month?)`
- `set_budget(month, category_id, limit_amount)` (admin/confirm)
- `add_account(id, display_name, type)` (admin)
- `adjust_account_balance(account_id, amount, note)` (admin/confirm)

**Important guardrails**
- If category or account is missing, the server returns `needs_clarification` with required fields, rather than guessing.
- The LLM should ask a follow-up question, then retry.

---

## 8) Error Handling Contract

All errors must be structured and predictable.

Example error response:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "from_account_id is required for expense transactions",
    "details": [
      { "field": "from_account_id", "issue": "missing" }
    ]
  }
}
```

For ambiguous inputs, return:
```json
{
  "error": {
    "code": "NEEDS_CLARIFICATION",
    "message": "Missing required fields to log transaction",
    "details": [
      { "field": "from_account_id", "question": "Which account did you pay from? (BCA/JAGO/CASH)" }
    ]
  }
}
```

---

## 9) Operational Spec

### 9.1 Deployment (single EC2)
- Run FastAPI on localhost (e.g., 127.0.0.1:8000).
- OpenClaw calls it over localhost.
- Reverse proxy (Caddy/Nginx) terminates TLS for OpenClaw webhook + optionally dashboard.

### 9.2 Logging
- Structured logs (JSON) with request id.
- Never log secrets.
- Store raw Discord message text only if needed; preferably store it in `metadata.raw_text`.

### 9.3 Backups
- Nightly job to copy SQLite DB file to S3 (recommended).
- Keep 7–30 days retention.

---

## 10) Implementation Checklist (MVP)

- [ ] Create FastAPI project + configuration (env vars: DB path, API key, timezone).
- [ ] Implement SQLite schema + migrations.
- [ ] Implement `/health`, `/v1/meta`.
- [ ] Implement transaction create + validation rules.
- [ ] Implement balances computation.
- [ ] Implement budget create/update + status computation.
- [ ] Implement summary endpoint.
- [ ] Implement dashboard pages (overview + transactions at minimum).
- [ ] Add API key middleware.
- [ ] Add tests for: expense, income, transfer, budgets, corrections.
- [ ] Add WAL mode, foreign keys pragma.
- [ ] Add backup script stub.
