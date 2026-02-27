# TOOLS.md — Finance API Cheat Sheet

## API Connection
- **Base URL:** `http://127.0.0.1:8000`
- **Auth:** `X-API-Key` header (via `$FINANCE_API_KEY`)
- **Skill:** `finance-api` — read its SKILL.md for curl patterns and tool JSON definitions for endpoint schemas

## Accounts

Each user has their own accounts. Account IDs are prefixed with the user's ID:

| ID | Name | Type | Owner |
|---|---|---|---|
| `fazrin_BCA` | BCA | bank | fazrin |
| `fazrin_JAGO` | Jago | bank | fazrin |
| `fazrin_CASH` | Cash | cash | fazrin |
| `fazrin_GOPAY` | GoPay | ewallet | fazrin |
| `fazrin_OVO` | OVO | ewallet | fazrin |
| `magfira_CBA` | CBA | bank | magfira |
| `magfira_CASH` | Cash | cash | magfira |

When a user logs a transaction, **default to their own accounts** (matching by owner_id). Call `GET /v1/accounts?user_id=<user_id>` to see the user's accounts.

New users won't have accounts yet — ask them to create one or just ask which account they want to use.

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
