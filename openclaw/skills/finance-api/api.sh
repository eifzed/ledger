#!/usr/bin/env bash
set -euo pipefail

# Finance API wrapper — handles base URL, auth, and content-type.
#
# Usage:
#   api.sh <METHOD> <PATH> [JSON_BODY]
#
# Examples:
#   api.sh GET /v1/accounts/balances
#   api.sh GET "/v1/transactions?month=2026-02&limit=5"
#   api.sh POST /v1/transactions '{"user_id":"fazrin","amount":50000,...}'
#   api.sh PUT /v1/budgets/2026-02/food '{"limit_amount":3000000}'

BASE_URL="${FINANCE_API_BASE_URL:-http://127.0.0.1:8000}"
API_KEY="${FINANCE_API_KEY:?FINANCE_API_KEY is not set}"

METHOD="${1:?Usage: api.sh <METHOD> <PATH> [JSON_BODY]}"
PATH_AND_QUERY="${2:?Usage: api.sh <METHOD> <PATH> [JSON_BODY]}"
BODY="${3:-}"

URL="${BASE_URL}${PATH_AND_QUERY}"

ARGS=(-s -X "$METHOD" "$URL" -H "X-API-Key: $API_KEY")

if [ -n "$BODY" ]; then
    ARGS+=(-H "Content-Type: application/json" -d "$BODY")
fi

curl "${ARGS[@]}"
