# USER.md — Users

Users are **auto-created** the first time they log a transaction. Use the sender's display name (lowercased) as the `user_id` — no pre-registration or mapping needed.

## Defaults
- **Currency:** IDR (Indonesian Rupiah). All amounts are integers, no decimals.
- If a user specifies a foreign currency (e.g. "200 AUD", "50 USD"), convert to IDR using live exchange rates and note the original amount in metadata.
- Users can tell the bot their preferred currency or location in chat; respect it for that session but always store transactions in IDR.

## Known Members

Some members use nicknames. Always map to the canonical `user_id`:

| Display name / aliases | user_id | Location | Timezone |
|---|---|---|---|
| Fazrin, eifzed | `fazrin` | Indonesia | Asia/Jakarta |
| Magfira, firrr | `magfira` | Australia | Australia/Sydney |

If the sender's display name matches any alias above (case-insensitive), use the canonical `user_id` — not the raw display name. For unknown names, lowercase the display name as usual.

### Timezone

When a user specifies a time, include their `timezone` field (IANA name from the table above) in the API request. The **backend handles DST and UTC conversion automatically** — you never need to calculate offsets.

- For known members, use the timezone from the table above.
- For unknown users, omit the `timezone` field (backend defaults to `Asia/Jakarta`).

## Household Context
- Budgets are typically household-level (shared) unless scoped to a specific user.
- Users log transactions via chat (Discord, WhatsApp, etc.).
