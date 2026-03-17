# Ledger

Household finance tracker with a Discord bot powered by [OpenClaw](https://docs.openclaw.ai), a web dashboard, and SQLite as the single source of truth. All calculations (balances, budgets, summaries) happen server-side.

## Architecture

```
Discord ──► OpenClaw Gateway ──► MCP server (stdio) ──► Service Layer ──► SQLite
                                                                            │
                                              Web Dashboard (SSR) ◄── FastAPI Routes ◄──┘
```

Two paths into the same data:

- **MCP server** (`mcp_server.py`) — Exposes the service layer as structured [MCP](https://modelcontextprotocol.io) tools. OpenClaw spawns it as a child process via stdio transport. The AI agent calls typed tools directly — no HTTP, no shell commands, no `curl`.
- **FastAPI** (`app/`) — RESTful API (`X-API-Key` auth) and server-rendered dashboard (Jinja2). Runs in Docker. Shares the same SQLite database and service layer as the MCP server.

Both paths call the same service functions (`app/services/`), so business logic is never duplicated.

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

### 3. Run the FastAPI server (dashboard + REST API)

```bash
uvicorn app.main:app --reload --port 8000
```

The server auto-creates the SQLite DB and seeds default users, categories, and accounts on first run.

### 4. Run the MCP server (for AI agent)

```bash
python mcp_server.py
```

This starts the MCP server on stdio transport. In practice, OpenClaw spawns it automatically — you only run it manually for testing.

### 5. Dashboard

Visit [http://localhost:8000](http://localhost:8000).

| Path | Description |
|------|-------------|
| `/` | Overview — totals, balances, budget bars, warnings |
| `/transactions` | Transaction list with filters and pagination |
| `/budgets` | Budget status with progress bars |
| `/accounts` | Account list with computed balances |

### Docker (dashboard only)

```bash
docker compose up --build
```

This runs the FastAPI server in Docker. The MCP server runs on the host (spawned by OpenClaw), sharing the same SQLite database via the mounted `./data` volume.

---

## API Reference (Dashboard + REST clients)

All endpoints (except `/health`) require `X-API-Key` header. These routes are used by the web dashboard and any REST clients. The AI agent does **not** use these routes — it calls MCP tools instead.

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

**Optional:** `currency` (default IDR), `description`, `merchant`, `payment_method` (cash\|qris\|debit\|credit\|bank_transfer\|ewallet\|other), `note`, `metadata`, `effective_at` (ISO 8601 with any timezone offset; the backend converts to UTC; defaults to now if omitted).

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

## MCP Tools (AI Agent)

The MCP server (`mcp_server.py`) exposes 17 tools that wrap the service layer. Each tool has typed parameters and structured return values — the AI agent never constructs HTTP requests or shell commands.

| Tool | Description |
|------|-------------|
| `create_transaction` | Create an expense, income, transfer, or adjustment |
| `list_transactions` | List with filters (month, category, user, account, search) |
| `get_transaction` | Get a single transaction by ID |
| `void_transaction` | Void (cancel) a transaction |
| `correct_transaction` | Void original + create replacement |
| `list_accounts` | List accounts (optionally by owner) |
| `get_account_balances` | Computed balances per account |
| `create_account` | Create a new account |
| `adjust_account_balance` | Credit or debit an account directly |
| `upsert_budget` | Set or update a monthly budget |
| `list_budgets` | List budgets for a month |
| `get_budget_status` | Budget usage, remaining, and warnings |
| `get_budget_history` | Budget change audit log |
| `get_monthly_summary` | Spending summary with breakdowns |
| `get_metadata` | Categories, accounts, users, server time |
| `convert_currency` | Live exchange rate conversion to IDR |
| `health_check` | Check if backend is operational |

Tool schemas are self-documenting — parameter names, types, and descriptions are embedded in the MCP tool definitions. The AI agent sees these schemas directly and calls tools with typed arguments.

---

## Seeded Data

On first run, the server seeds:

**Users:** `fazrin` (Fazrin), `magfira` (Magfira) — additional users are auto-created on first transaction

**Accounts** — every known user gets all 6 account types, prefixed with their `user_id`:

| Suffix | Name | Type |
|--------|------|------|
| `_BCA` | BCA | bank |
| `_JAGO` | Jago | bank |
| `_CBA` | CBA | bank |
| `_CASH` | Cash | cash |
| `_GOPAY` | GoPay | ewallet |
| `_OVO` | OVO | ewallet |

For example: `fazrin_BCA`, `fazrin_JAGO`, `magfira_CBA`, `magfira_GOPAY`, etc. (12 accounts total for 2 users). The backend auto-resolves unprefixed names (e.g. `"BCA"` → `fazrin_BCA` for user fazrin).

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

The bot connects to Discord via [OpenClaw](https://docs.openclaw.ai) and uses MCP tools to interact with the Ledger service layer directly. Users speak natural language in Discord — the bot parses messages, calls MCP tools, and formats responses.

### How It Works

1. OpenClaw injects **system prompt files** (AGENTS.md, SOUL.md, etc.) into the agent's context at the start of each session.
2. OpenClaw spawns the **MCP server** (`mcp_server.py`) as a child process via stdio transport.
3. The agent sees all 17 MCP tools with their typed schemas — parameter names, types, descriptions, and required/optional markers.
4. When the user sends a finance message, the agent calls the appropriate MCP tool with structured arguments.
5. The MCP tool executes the service layer function directly (no HTTP) and returns structured data.
6. The agent formats the response into a Discord-friendly message.

### File Structure

```
openclaw/
├── prompt/                    # System prompt files (copied to OpenClaw workspace root)
│   ├── AGENTS.md              # Behavioral rules: user_id extraction, receipt formatting,
│   │                          # time parsing, category inference, clarification UX, safety
│   ├── IDENTITY.md            # Bot name, persona, emoji
│   ├── SOUL.md                # Behavioral philosophy and boundaries
│   ├── USER.md                # Known users, aliases, timezones, auto-creation rules
│   ├── TOOLS.md               # Reference data: accounts, categories, amount shorthands,
│   │                          # payment methods, transaction types
│   ├── BOOTSTRAP.md           # First-run setup checklist and intro message
│   └── HEARTBEAT.md           # Periodic tasks (budget threshold alerts)
│
├── skills/
│   └── finance-api/
│       ├── SKILL.md            # Skill metadata (mcp: true) + domain rules and error codes
│       └── tools/              # JSON schema definitions per tool (reference only)
│           ├── create_transaction.json
│           ├── list_transactions.json
│           └── ...
│
mcp_server.py                  # MCP tool server — wraps service layer as MCP tools
```

### Prompt Design

The system prompt is intentionally lean. With MCP tools, the AI agent sees typed schemas directly, so the prompts focus only on things schemas can't express:

| File | What it covers |
|------|----------------|
| `AGENTS.md` | How to extract `user_id` from Discord sender context, receipt formatting, time parsing from natural language, Indonesian slang → category mapping, clarification UX, display formats, safety rules |
| `SOUL.md` | Persona: precise with money, casual with words. Hard boundaries (never calculate, never fabricate). |
| `USER.md` | Known household members, aliases (firrr → magfira), timezones. |
| `TOOLS.md` | Reference data the agent needs to interpret messages: account suffixes, category tree, Indonesian amount shorthands (50k, 1jt, gopek, ceban). |
| `SKILL.md` | Minimal — just metadata (`mcp: true`), five domain rules, and error codes. Tool parameters are self-documented via MCP schemas. |

### Setting Up OpenClaw

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
cp openclaw/skills/finance-api/tools/*.json "$OPENCLAW_WS/skills/finance-api/tools/"
```

4. **Configure the MCP client** in your OpenClaw agent config to spawn the MCP server:

```json
{
  "mcpServers": {
    "ledger": {
      "command": "/path/to/ledger/.venv/bin/python",
      "args": ["/path/to/ledger/mcp_server.py"],
      "env": {
        "LEDGER_DB_PATH": "/path/to/ledger/data/ledger.db"
      }
    }
  }
}
```

5. **Verify the skill is loaded:**

```bash
openclaw skills list
```

Look for `finance-api` with status `✓ ready` and source `openclaw-workspace`.

6. **Restart the gateway:**

```bash
openclaw gateway restart
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Bot doesn't call any tools | MCP server not configured in agent | Add `mcpServers.ledger` to the agent config (see step 4 above) |
| MCP server exits immediately | Missing dependencies | Run `pip install -r requirements.txt` in the venv that OpenClaw uses to spawn the server |
| Bot asks for user_id | Not extracting sender name | Check `AGENTS.md` has the user_id extraction rules. Check `USER.md` has the correct aliases. |
| `NOT_FOUND` errors for accounts | User has no accounts yet | New users are auto-created but need accounts. Use `create_account` or check seeded data. |
| Skill not showing in `openclaw skills list` | Files not in the right location | Skill must be at `<workspace>/skills/finance-api/SKILL.md` with valid YAML frontmatter |

---

## Project Structure

```
ledger/
├── mcp_server.py               # MCP tool server — wraps service layer for AI agent (stdio)
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
│   ├── services/               # Business logic (shared by MCP server + FastAPI routes)
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
├── openclaw/                   # OpenClaw bot configuration (see "OpenClaw Integration" above)
│   ├── prompt/
│   └── skills/finance-api/
├── tests/
│   ├── conftest.py             # Prompt regression test infrastructure (loads prompts, defines tool schemas)
│   ├── test_bot_behavior.py    # 74 behavioral tests — validates LLM produces correct tool calls
│   └── test_mcp_tools.py       # 51 integration tests — validates MCP tools against real DB
├── data/                       # SQLite database (gitignored)
├── .env.example
├── .github/workflows/deploy.yml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── spec/spec.md                # Original API specification
```

---

## Tests

```bash
# MCP tool integration tests (no API key needed)
.venv/bin/python -m pytest tests/test_mcp_tools.py -v

# Prompt regression tests (requires OPENAI_API_KEY in .env)
.venv/bin/python -m pytest tests/test_bot_behavior.py -v
```

- **`test_mcp_tools.py`** (51 tests) — Calls MCP tool functions directly against an in-memory SQLite database. Covers happy paths, error handling, account ownership enforcement, voided transaction exclusion, and JSON serialization.
- **`test_bot_behavior.py`** (74 tests) — Sends natural language messages to an LLM with the system prompt and tool schemas, then asserts that the LLM produces the correct tool calls with correct arguments. Covers user_id extraction, amount parsing, intent detection, category inference, time parsing, timezone handling, currency conversion, multi-item, revision flow, clarification, and safety.

---

## Deployment

### GitHub Actions

On push to `main`, `.github/workflows/deploy.yml`:

1. SSHs into the EC2 instance
2. Pulls latest code
3. Rebuilds and restarts the Docker container (FastAPI + dashboard)
4. Creates/updates a Python venv on the host and installs dependencies (for the MCP server)
5. Copies prompt files and skill files to the OpenClaw workspace
6. Restarts the OpenClaw gateway and clears Discord sessions

The MCP server runs on the host (spawned by OpenClaw via stdio), while FastAPI runs in Docker. Both share the same SQLite database through the mounted `./data` volume.

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `EC2_HOST` | EC2 public IP or hostname |
| `EC2_USER` | SSH username (e.g. `ubuntu`) |
| `EC2_SSH_KEY` | Private SSH key for the EC2 instance |
| `APP_DIR` | Path to the cloned repo on EC2 |
| `OPENCLAW_WORKSPACE` | Path to OpenClaw workspace (e.g. `~/.openclaw/workspace`) |
