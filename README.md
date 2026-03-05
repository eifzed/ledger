# Ledger

Household finance tracker with a FastAPI backend, web dashboard, and a Discord bot powered by [OpenClaw](https://docs.openclaw.ai). SQLite is the single source of truth — all calculations (balances, budgets, summaries) happen server-side.

## Architecture

```
Discord ──► OpenClaw Gateway ──► exec: curl ──► FastAPI Backend ──► SQLite
                                                     │
                                          Web Dashboard (SSR)
```

- **FastAPI Backend** — RESTful API for transactions, accounts, budgets, summaries. Authenticated with `X-API-Key` header.
- **Web Dashboard** — Server-rendered HTML pages (Jinja2) for viewing data in a browser.
- **OpenClaw** — AI agent platform that connects to Discord. It reads system prompt files and a custom `finance-api` skill to translate natural language into API calls.

---

## Quick Start

### 1. Clone and install

```bash
git clone <repo-url> && cd ledger
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `LEDGER_DB_PATH` | Path to SQLite database | `./data/ledger.db` |
| `LEDGER_API_KEY` | API key for `X-API-Key` header | `change-me-in-production` |
| `LEDGER_TIMEZONE` | Server timezone | `Asia/Jakarta` |
| `LEDGER_DASH_USER` | Dashboard login username | `admin` |
| `LEDGER_DASH_PASS` | Dashboard login password | `change-me` |
| `LEDGER_SECRET_KEY` | Session signing key | `ledger-secret-change-me` |

### 3. Run

```bash
uvicorn app.main:app --reload --port 8000
```

The server auto-creates the SQLite DB and seeds default users, categories, and accounts on first run.

### 4. Dashboard

Visit [http://localhost:8000](http://localhost:8000).

| Path | Description |
|------|-------------|
| `/` | Overview — totals, balances, budget bars, warnings |
| `/transactions` | Transaction list with filters and pagination |
| `/budgets` | Budget status with progress bars |
| `/accounts` | Account list with computed balances |

### Docker

```bash
docker compose up --build
```

---

## API Reference

All endpoints (except `/health`) require `X-API-Key` header.

### Health

```
GET /health
```

### Metadata

```
GET /v1/meta
```

Returns all categories, accounts, users, payment methods, transaction types, and server time.

### Transactions

```
POST   /v1/transactions                          # Create
GET    /v1/transactions?month=YYYY-MM&limit=50   # List (filters: category_id, user_id, account_id, search, offset)
GET    /v1/transactions/{id}                      # Get one (id is an integer)
POST   /v1/transactions/{id}/void                 # Void (irreversible)
POST   /v1/transactions/{id}/correct              # Correct (voids original + creates replacement)
```

Transaction IDs are auto-incrementing integers (1, 2, 3, ...). Users are auto-created on their first transaction.

**Create body:**

```json
{
  "user_id": "fazrin",
  "transaction_type": "expense",
  "amount": 65000,
  "category_id": "groceries",
  "from_account_id": "fazrin_BCA",
  "description": "detergent",
  "merchant": "Indomaret",
  "payment_method": "qris",
  "effective_at": "2026-02-25T05:00:00+07:00",
  "metadata": {"raw_text": "beli detergent 65k qris bca at 5am"}
}
```

**Required fields by type:**

| Type | Required | Notes |
|------|----------|-------|
| `expense` | `user_id`, `amount`, `category_id`, `from_account_id` | `to_account_id` must be null |
| `income` | `user_id`, `amount`, `to_account_id` | |
| `transfer` | `user_id`, `amount`, `from_account_id`, `to_account_id` | |
| `adjustment` | `user_id`, `amount` | |

**Optional:** `currency` (default IDR), `description`, `merchant`, `payment_method` (cash\|qris\|debit\|credit\|bank_transfer\|ewallet\|other), `note`, `metadata`, `effective_at` (ISO 8601 with any timezone offset, e.g. `2026-02-25T05:00:00+07:00`; the backend converts to UTC before storing; defaults to current UTC time if omitted).

**Response** includes: `transaction` (with integer `id`), `balances`, `budget_status`, `warnings`.

### Budgets

```
GET  /v1/budgets/status?month=YYYY-MM             # Status with usage/remaining/warnings
GET  /v1/budgets?month=YYYY-MM                     # List raw budgets
PUT  /v1/budgets/{month}/{category_id}             # Upsert (parent categories only)
GET  /v1/budgets/history?month=YYYY-MM&limit=50    # Audit log
```

### Accounts

```
GET   /v1/accounts?user_id=fazrin             # List (optional user_id filter by owner)
GET   /v1/accounts/balances?user_id=fazrin    # Computed balances (optional user_id filter)
POST  /v1/accounts                            # Create (types: bank, cash, ewallet, credit_card, other; include owner_id)
POST  /v1/accounts/{id}/adjust                # Adjust balance (positive=credit, negative=debit)
```

Accounts have an `owner_id` field. Use `?user_id=` to filter by owner; omit for all accounts.

### Summary

```
GET /v1/summary/monthly?month=YYYY-MM&user_id=fazrin
```

Returns: `total_expenses`, `total_income`, `net`, `by_category`, `by_user`, `daily_totals`, `top_merchants`, `budget_status`, `warnings`. The `user_id` parameter is optional — omit for household totals.

### Error Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "from_account_id is required for expense transactions",
    "details": [{"field": "from_account_id", "issue": "missing"}]
  }
}
```

Error codes: `VALIDATION_ERROR`, `NEEDS_CLARIFICATION`, `NOT_FOUND`, `DUPLICATE`.

---

## Seeded Data

On first run, the server seeds:

**Users:** `fazrin` (Fazrin), `magfira` (Magfira) — additional users are auto-created on first transaction

**Accounts** (per-user, prefixed with owner ID):

| ID | Name | Type | Owner |
|----|------|------|-------|
| `fazrin_BCA` | BCA | bank | fazrin |
| `fazrin_JAGO` | Jago | bank | fazrin |
| `fazrin_CASH` | Cash | cash | fazrin |
| `fazrin_GOPAY` | GoPay | ewallet | fazrin |
| `fazrin_OVO` | OVO | ewallet | fazrin |
| `magfira_CBA` | CBA | bank | magfira |
| `magfira_CASH` | Cash | cash | magfira |

Each user's accounts are prefixed with their `user_id`. Transactions default to the user's own accounts unless specified otherwise.

**Categories** (parent → subcategories, use subcategory IDs when possible):

- **food**: groceries, eating_out, coffee, delivery
- **transport**: fuel, parking, toll, public_transport, ride_hailing
- **bills**: electricity, water, internet, phone, gas_lpg, subscriptions
- **housing**: rent, furnishing, maintenance, cleaning
- **shopping**: clothing, electronics, household_items
- **health**: medical, pharmacy, gym
- **entertainment**: movies, games, hobbies, outings
- **vehicle**: car_service, car_insurance, car_tax
- **personal**: haircut, skincare
- **education**: courses, books
- **gifts**: gifts_items, charity, zakat
- **investment**: gold, stock, bond, saving
- **income**: salary, freelance, other_income

Budgets can only be set on **parent** categories.

---

## OpenClaw Integration (Discord Bot)

The bot connects to Discord via [OpenClaw](https://docs.openclaw.ai) and uses the Ledger API as its backend. Users interact through natural language in Discord — the bot parses messages, calls the API, and formats responses.

### How It Works

1. OpenClaw injects **system prompt files** (AGENTS.md, SOUL.md, etc.) into the agent's context at the start of each session.
2. The agent sees a list of available **skills**, including `finance-api`, with a short description.
3. When the user sends a finance command, the agent reads the `finance-api` SKILL.md to find the exact `curl` command pattern.
4. The agent uses the `exec` tool to run `curl` with the `$FINANCE_API_KEY` env var for authentication.
5. The agent formats the JSON response into Discord-friendly messages.

### File Structure

```
openclaw/
├── prompt/                    # System prompt files (copied to OpenClaw workspace root)
│   ├── AGENTS.md              # Core instructions: how to call the API, command definitions,
│   │                          # clarification rules, formatting, safety guardrails
│   ├── IDENTITY.md            # Bot name, persona, emoji
│   ├── SOUL.md                # Behavioral philosophy and boundaries
│   ├── USER.md                # User handling: auto-creation, default currency
│   ├── TOOLS.md               # Quick-reference cheat sheet: accounts, categories,
│   │                          # amount shorthands, payment methods
│   ├── BOOTSTRAP.md           # First-run setup checklist and intro message
│   └── HEARTBEAT.md           # Periodic tasks (budget threshold alerts)
│
└── skills/
    └── finance-api/
        ├── SKILL.md            # Skill definition with complete curl examples for every endpoint
        ├── api.sh              # Shell wrapper for curl (handles base URL + auth header)
        └── tools/              # JSON schema definitions per endpoint (reference only)
            ├── create_transaction.json
            ├── list_transactions.json
            ├── get_account_balances.json
            └── ...
```

### System Prompt Files

OpenClaw builds a system prompt by injecting these Markdown files into the agent's context. Each file has a specific role:

| File | Purpose |
|------|---------|
| `AGENTS.md` | The main instruction set. Defines how to call the API (always `exec` with `curl`), natural language intent detection (recording, revising, balances, budgets, summaries), time parsing rules, foreign currency conversion via `/v1/convert`, clarification rules, formatting rules, and safety constraints. No slash commands — the bot understands plain language. |
| `IDENTITY.md` | Bot name ("Ledger"), persona, and emoji. |
| `SOUL.md` | Behavioral guide: be precise with money, casual with words, proactive but not annoying. Defines language style and hard boundaries. |
| `USER.md` | User handling: auto-creation from Discord display names, default currency (IDR), known household members with timezones (Fazrin in Jakarta UTC+7, Magfira in Sydney UTC+11). |
| `TOOLS.md` | Quick-reference for accounts, categories, amount shorthands (50k=50000, 1.5jt=1500000), payment methods, and transaction types. Keeps this info out of AGENTS.md to reduce prompt size. |
| `BOOTSTRAP.md` | One-time first-run instructions. The agent introduces itself and verifies the API is online. |
| `HEARTBEAT.md` | Periodic task definition. Checks budget status and alerts if any category exceeds 80%. |

### The `finance-api` Skill

The skill (`openclaw/skills/finance-api/SKILL.md`) teaches the agent how to call the Ledger API. It contains:

- **Frontmatter** declaring the skill name, description, and required env vars
- **Complete curl examples** for every API endpoint
- **Request schemas** (required/optional fields per transaction type)
- **Error handling guidance**

Key design decisions:

- **`user-invocable: false`** — The skill is NOT exposed as a Discord slash command. It's a reference document the agent reads when it needs to make API calls.
- **Inline curl commands** — Each example includes the full `curl` command with `$FINANCE_API_KEY`. This is intentional: OpenClaw's `{baseDir}` template variable only resolves inside skill invocations, NOT when the agent reads the file with the `read` tool. Using inline curl with env vars avoids path-resolution issues.
- **`exec` tool only** — The agent must use OpenClaw's `exec` tool to run curl. The `web_fetch` tool cannot send custom headers, so API calls through `web_fetch` fail with 401.

### Setting Up OpenClaw (Local)

**Prerequisites:** [OpenClaw CLI](https://docs.openclaw.ai) installed, Node >= 22.12.0, Discord bot token.

1. **Run the onboarding wizard:**

```bash
openclaw onboard
```

Configure your Discord token, OpenAI API key, and workspace path (default: `~/.openclaw/workspace`).

2. **Copy prompt files to the workspace:**

```bash
OPENCLAW_WS=~/.openclaw/workspace
cp openclaw/prompt/*.md "$OPENCLAW_WS/"
```

3. **Copy the skill:**

```bash
mkdir -p "$OPENCLAW_WS/skills/finance-api/tools"
cp openclaw/skills/finance-api/SKILL.md "$OPENCLAW_WS/skills/finance-api/"
cp openclaw/skills/finance-api/api.sh "$OPENCLAW_WS/skills/finance-api/"
chmod +x "$OPENCLAW_WS/skills/finance-api/api.sh"
cp openclaw/skills/finance-api/tools/*.json "$OPENCLAW_WS/skills/finance-api/tools/"
```

4. **Set the API key:**

```bash
echo 'FINANCE_API_KEY=<your-LEDGER_API_KEY-value>' >> ~/.openclaw/.env
```

Use the same value as `LEDGER_API_KEY` in the backend's `.env`.

5. **Verify the skill is loaded:**

```bash
openclaw skills list
```

Look for `finance-api` with status `✓ ready` and source `openclaw-workspace`.

6. **Restart the gateway:**

```bash
openclaw gateway restart
```

7. **Test:**

```bash
openclaw agent --session-id test --message "/balance" --json
```

### Setting Up OpenClaw (EC2 / Production)

Same steps as local, plus:

- Add `FINANCE_API_KEY` to `~/.openclaw/.env` on the server
- The GitHub Actions workflow (`.github/workflows/deploy.yml`) automatically syncs prompt and skill files, restarts the gateway, and clears Discord sessions on merge to `main`

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Bot says "command not found" | It's trying to run `finance-api` as a CLI binary | Verify `SKILL.md` has `user-invocable: false` and `AGENTS.md` instructs `exec` with `curl` |
| 401 Unauthorized from API | Missing `X-API-Key` header | Bot is using `web_fetch` instead of `exec` with `curl`. Check `AGENTS.md` has the `web_fetch` prohibition. Also verify `FINANCE_API_KEY` is set in `~/.openclaw/.env` |
| Bot can't find `api.sh` / `{baseDir}` errors | `{baseDir}` doesn't resolve in `read` tool output | Use inline curl commands in SKILL.md (current approach) instead of `{baseDir}/api.sh` references |
| Bot asks for user_id on Discord | Not extracting sender name from Discord message | `AGENTS.md` instructs the bot to lowercase the sender's display name and use it as `user_id`. Users are auto-created on first transaction. |
| Skill not showing in `openclaw skills list` | Files not in the right location | Skill must be at `<workspace>/skills/finance-api/SKILL.md` with valid YAML frontmatter |

---

## Project Structure

```
ledger/
├── app/
│   ├── main.py                 # FastAPI entry point, lifespan, exception handlers
│   ├── config.py               # Pydantic settings from env (LEDGER_* prefix)
│   ├── database.py             # SQLAlchemy engine + session factory
│   ├── models.py               # ORM models (User, Account, Category, Transaction, Budget)
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── auth.py                 # X-API-Key middleware
│   ├── errors.py               # Structured error handling (NEEDS_CLARIFICATION, etc.)
│   ├── seed.py                 # Default data seeding (users, categories, accounts)
│   ├── tz.py                   # Timezone utilities
│   ├── routers/
│   │   ├── health.py           # GET /health
│   │   ├── meta.py             # GET /v1/meta
│   │   ├── transactions.py     # Transaction CRUD + void + correct
│   │   ├── budgets.py          # Budget CRUD + status + history
│   │   ├── accounts.py         # Account CRUD + balances + adjust
│   │   ├── summary.py          # GET /v1/summary/monthly
│   │   └── dashboard.py        # Server-rendered HTML pages
│   ├── services/
│   │   ├── transaction_service.py
│   │   ├── budget_service.py
│   │   ├── account_service.py
│   │   └── summary_service.py
│   └── templates/              # Jinja2 templates for web dashboard
│       ├── base.html
│       ├── overview.html
│       ├── transactions.html
│       ├── budgets.html
│       ├── accounts.html
│       └── login.html
├── alembic/                    # Database migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_category_hierarchy.py
│       └── 003_budget_snapshots.py
├── openclaw/                   # OpenClaw bot configuration (see "OpenClaw Integration" above)
│   ├── prompt/
│   └── skills/finance-api/
├── data/                       # SQLite database (gitignored)
├── .env.example
├── .github/workflows/deploy.yml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── spec/spec.md                # Original API specification
```

---

## Deployment

### GitHub Actions

On push to `main`, `.github/workflows/deploy.yml`:

1. SSHs into the EC2 instance
2. Pulls latest code
3. Rebuilds and restarts the Docker container
4. Copies prompt files and skill files to the OpenClaw workspace
5. Restarts the OpenClaw gateway
6. Clears Discord sessions (so the bot picks up updated prompts/skills immediately)

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `EC2_HOST` | EC2 public IP or hostname |
| `EC2_USER` | SSH username (e.g. `ubuntu`) |
| `EC2_SSH_KEY` | Private SSH key for the EC2 instance |
| `APP_DIR` | Path to the cloned repo on EC2 |
| `OPENCLAW_WORKSPACE` | Path to OpenClaw workspace (e.g. `~/.openclaw/workspace`) |
