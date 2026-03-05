# TOOLS.md — Finance API Cheat Sheet

## API Connection
- **Base URL:** `http://127.0.0.1:8000`
- **Auth:** `X-API-Key` header (via `$FINANCE_API_KEY`)
- **Skill:** `finance-api` — read its SKILL.md for curl patterns and tool JSON definitions for endpoint schemas
- **Timezone:** All stored datetimes are **UTC**. API responses return UTC (`+00:00`). Send `effective_at` with the user's local timezone offset — the backend converts to UTC automatically.

## Accounts

Each user has their own copy of every account. Account IDs are prefixed with the user's ID:

| Suffix | Name | Type |
|---|---|---|
| `BCA` | BCA | bank |
| `JAGO` | Jago | bank |
| `CBA` | CBA | bank |
| `CASH` | Cash | cash |
| `GOPAY` | GoPay | ewallet |
| `OVO` | OVO | ewallet |

Every known user gets all of the above (e.g. `fazrin_BCA`, `magfira_BCA`, `fazrin_CBA`, `magfira_CBA`, etc.).

When a user logs a transaction, **always use their own accounts**. The backend enforces this — using another user's account will be rejected.

You can send just the display name (e.g. `"Cash"`, `"BCA"`) as the account ID and the backend will auto-resolve it to the user's prefixed account (e.g. `"Cash"` → `magfira_CASH` for user magfira).

Call `GET /v1/accounts?user_id=<user_id>` to see a user's accounts. New users won't have accounts yet — ask them to create one.

If the user says QRIS, the *payment_method* is `qris` — but you still need to know which account was charged.

## Categories

Parent → subcategories. Use the **subcategory** ID when one fits.

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

Budgets can only be set on **parent** categories (e.g. `food`, not `groceries`).

## Amount Shorthands

| Input | Means | IDR |
|---|---|---|
| `50k`, `50rb` | 50 ribu | 50000 |
| `2.5k` | 2.5 ribu | 2500 |
| `1.5jt` | 1.5 juta | 1500000 |
| `ceban` | slang 10k | 10000 |
| `goban` | slang 50k | 50000 |
| `cepek` | slang 100k | 100000 |

## Payment Methods

`cash`, `qris`, `debit`, `credit`, `bank_transfer`, `ewallet`, `other`

## Transaction Types

`expense`, `income`, `transfer`, `adjustment`
