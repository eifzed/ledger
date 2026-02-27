# USER.md — Users

Users are **auto-created** the first time they log a transaction. Use the sender's Discord display name (lowercased) as the `user_id` — no pre-registration or mapping needed.

## Defaults
- **Currency:** IDR (Indonesian Rupiah). All amounts are integers, no decimals.
- If a user specifies a foreign currency (e.g. "200 AUD", "50 USD"), convert to IDR using live exchange rates and note the original amount in metadata.
- Users can tell the bot their preferred currency or location in chat; respect it for that session but always store transactions in IDR.

## Known Members
- **Fazrin** — based in Indonesia (Asia/Jakarta, UTC+7)
- **Magfira** — based in Australia (Australia/Sydney, UTC+11). Fazrin's wife.

## Household Context
- Budgets are typically household-level (shared) unless scoped to a specific user.
- Users log transactions via Discord.
- When parsing times, use the user's timezone based on the known members list above. Default to Asia/Jakarta for unknown users.
