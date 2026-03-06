# USER.md — Users

Users are **auto-created** the first time they log a transaction. Use the sender's Discord display name (lowercased) as the `user_id` — no pre-registration or mapping needed.

## Defaults
- **Currency:** IDR (Indonesian Rupiah). All amounts are integers, no decimals.
- If a user specifies a foreign currency (e.g. "200 AUD", "50 USD"), convert to IDR using live exchange rates and note the original amount in metadata.
- Users can tell the bot their preferred currency or location in chat; respect it for that session but always store transactions in IDR.

## Known Members

Some members use nicknames on Discord. Always map to the canonical `user_id`:

| Discord display name | user_id | Location | Timezone |
|---|---|---|---|
| Fazrin, eifzed | `fazrin` | Indonesia | Asia/Jakarta (UTC+7) |
| Magfira, firrr | `magfira` | Australia | Australia/Sydney (UTC+11) |

If the sender's display name matches any alias above (case-insensitive), use the canonical `user_id` — not the raw display name. For unknown names, lowercase the display name as usual.

## Household Context
- Budgets are typically household-level (shared) unless scoped to a specific user.
- Users log transactions via Discord.
- When parsing times, use the user's timezone based on the known members list above. Default to Asia/Jakarta for unknown users.
