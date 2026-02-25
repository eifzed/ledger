# Ledger — Household Finance API + Dashboard

A tool-friendly HTTP API for household finance management, designed to work with a Discord bot (OpenClaw). SQLite is the single source of truth. All calculations (balances, budgets, summaries) happen server-side.

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your API key
```

### 3. Run

```bash
uvicorn app.main:app --reload --port 8000
```

The server auto-creates the SQLite DB and seeds default users, categories, and accounts on first run.

### 4. Open the dashboard

Visit [http://localhost:8000](http://localhost:8000) for the web dashboard.

## Docker

```bash
docker compose up --build
```

---

## API Overview

All API endpoints (except `/health`) require the `X-API-Key` header.

### Health

```bash
curl http://localhost:8000/health
```

### Metadata

```bash
curl -H "X-API-Key: change-me-in-production" \
  http://localhost:8000/v1/meta
```

### Create an Expense

```bash
curl -X POST http://localhost:8000/v1/transactions \
  -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "fazrin",
    "transaction_type": "expense",
    "amount": 65000,
    "category_id": "groceries",
    "description": "detergent indomaret",
    "merchant": "Indomaret",
    "payment_method": "qris",
    "from_account_id": "BCA"
  }'
```

### Log Income

```bash
curl -X POST http://localhost:8000/v1/transactions \
  -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "fazrin",
    "transaction_type": "income",
    "amount": 15000000,
    "category_id": "salary",
    "description": "February salary",
    "to_account_id": "BCA"
  }'
```

### Log Transfer

```bash
curl -X POST http://localhost:8000/v1/transactions \
  -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "fazrin",
    "transaction_type": "transfer",
    "amount": 2000000,
    "description": "Move to Jago savings",
    "from_account_id": "BCA",
    "to_account_id": "JAGO"
  }'
```

### List Transactions

```bash
curl -H "X-API-Key: change-me-in-production" \
  "http://localhost:8000/v1/transactions?month=2026-02&limit=20"
```

### Get Single Transaction

```bash
curl -H "X-API-Key: change-me-in-production" \
  http://localhost:8000/v1/transactions/{id}
```

### Void a Transaction

```bash
curl -X POST -H "X-API-Key: change-me-in-production" \
  http://localhost:8000/v1/transactions/{id}/void
```

### Set a Budget

```bash
curl -X PUT http://localhost:8000/v1/budgets/2026-02/groceries \
  -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"limit_amount": 3000000}'
```

### Get Budget Status

```bash
curl -H "X-API-Key: change-me-in-production" \
  "http://localhost:8000/v1/budgets/status?month=2026-02"
```

### List Accounts

```bash
curl -H "X-API-Key: change-me-in-production" \
  http://localhost:8000/v1/accounts
```

### Get Account Balances

```bash
curl -H "X-API-Key: change-me-in-production" \
  http://localhost:8000/v1/accounts/balances
```

### Adjust Account Balance

```bash
curl -X POST http://localhost:8000/v1/accounts/BCA/adjust \
  -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000000, "user_id": "fazrin", "note": "Initial balance"}'
```

### Create Account

```bash
curl -X POST http://localhost:8000/v1/accounts \
  -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"id": "DANA", "display_name": "DANA", "type": "ewallet"}'
```

### Monthly Summary

```bash
curl -H "X-API-Key: change-me-in-production" \
  "http://localhost:8000/v1/summary/monthly?month=2026-02"
```

---

## Dashboard Pages

| Path | Description |
|------|-------------|
| `/` | Overview — totals, balances, budget bars, warnings |
| `/transactions` | Transaction list with filters and pagination |
| `/budgets` | Budget status with progress bars |
| `/accounts` | Account list with computed balances |

---

## Project Structure

```
app/
  main.py            # FastAPI entry point
  config.py          # Settings from env
  database.py        # SQLAlchemy engine + session
  models.py          # ORM models
  schemas.py         # Pydantic request/response models
  auth.py            # API key middleware
  errors.py          # Structured error handling
  seed.py            # Default data seeding
  tz.py              # Timezone utilities
  routers/
    health.py        # GET /health
    meta.py          # GET /v1/meta
    transactions.py  # Transaction CRUD
    budgets.py       # Budget CRUD + status
    accounts.py      # Account CRUD + balances
    summary.py       # Monthly summary
    dashboard.py     # Server-rendered HTML pages
  services/
    transaction_service.py
    budget_service.py
    account_service.py
    summary_service.py
  templates/
    base.html
    overview.html
    transactions.html
    budgets.html
    accounts.html
alembic/             # DB migrations
```

## Error Format

All errors return a structured JSON envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "from_account_id is required for expense transactions",
    "details": [{"field": "from_account_id", "issue": "missing"}]
  }
}
```

When the bot sends incomplete data, the server returns `NEEDS_CLARIFICATION`:

```json
{
  "error": {
    "code": "NEEDS_CLARIFICATION",
    "message": "Missing required fields to log transaction",
    "details": [
      {"field": "from_account_id", "question": "Which account did you pay from?"}
    ]
  }
}
```
