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
| Fazrin, eifzed | `fazrin` | Indonesia | Asia/Jakarta |
| Magfira, firrr | `magfira` | Australia | Australia/Sydney |

If the sender's display name matches any alias above (case-insensitive), use the canonical `user_id` — not the raw display name. For unknown names, lowercase the display name as usual.

### Timezone Offsets (DST-aware)

Do NOT hardcode UTC offsets. Derive the correct offset from the timezone name and the current date (use `server_time` from `/v1/meta`):

- **Asia/Jakarta** → always UTC+7 (no DST)
- **Australia/Sydney** → UTC+11 during AEDT (first Sunday in October → first Sunday in April), UTC+10 during AEST (first Sunday in April → first Sunday in October)

**To determine the offset:** Check the month from `server_time`. If the current date falls within AEDT (roughly Oct–Mar), use `+11:00`. If it falls within AEST (roughly Apr–Sep), use `+10:00`. For dates near the transition (first Sunday of April or October), reason about the exact day.

Unknown users default to `Asia/Jakarta` (UTC+7).

## Household Context
- Budgets are typically household-level (shared) unless scoped to a specific user.
- Users log transactions via Discord.
- When parsing times, use the user's timezone based on the known members list above. Default to Asia/Jakarta for unknown users.
