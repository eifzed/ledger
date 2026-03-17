# TOOLS.md — Reference Data

## Accounts

Each user has their own accounts. Account IDs are prefixed with the user's ID:

| Suffix | Name | Type |
|---|---|---|
| `BCA` | BCA | bank |
| `JAGO` | Jago | bank |
| `CBA` | CBA | bank |
| `CASH` | Cash | cash |
| `GOPAY` | GoPay | ewallet |
| `OVO` | OVO | ewallet |

Every known user gets all of the above (e.g. `fazrin_BCA`, `magfira_BCA`). Send just the display name (e.g. `"Cash"`, `"BCA"`) — the backend resolves it.

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
| `1jt`, `sejuta` | 1 juta | 1000000 |
| `1.5jt` | 1.5 juta | 1500000 |
| `gopek` | slang 500 | 500 |
| `seceng` | slang 1k | 1000 |
| `goceng` | slang 5k | 5000 |
| `ceban` | slang 10k | 10000 |
| `goban` | slang 50k | 50000 |
| `cepek` | slang 100k | 100000 |
| `nopek` | slang 900k | 900000 |

## Payment Methods

`cash`, `qris`, `debit`, `credit`, `bank_transfer`, `ewallet`, `other`

## Transaction Types

`expense`, `income`, `transfer`, `adjustment`
