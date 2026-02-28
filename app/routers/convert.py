"""Currency conversion endpoint using open.er-api.com."""

import httpx
from fastapi import APIRouter, Depends, Query

from app.auth import require_api_key
from app.errors import LedgerHTTPException

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])

_RATE_API = "https://open.er-api.com/v6/latest"


@router.get("/convert")
async def convert_currency(
    amount: float = Query(..., gt=0, description="Amount in source currency"),
    from_currency: str = Query(..., alias="from", min_length=3, max_length=3, description="Source currency code (e.g. AUD)"),
    to: str = Query("IDR", min_length=3, max_length=3, description="Target currency code"),
):
    from_code = from_currency.upper()
    to_code = to.upper()

    if from_code == to_code:
        return {
            "from": from_code,
            "to": to_code,
            "amount": amount,
            "rate": 1.0,
            "result": round(amount),
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_RATE_API}/{from_code}")
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise LedgerHTTPException(502, "CONVERSION_ERROR", f"Failed to fetch exchange rate: {exc}")

    if data.get("result") != "success":
        raise LedgerHTTPException(502, "CONVERSION_ERROR", f"Exchange rate API error: {data.get('error-type', 'unknown')}")

    rates = data.get("rates", {})
    if to_code not in rates:
        raise LedgerHTTPException(400, "VALIDATION_ERROR", f"Unknown target currency: {to_code}")

    rate = rates[to_code]
    result = round(amount * rate)

    return {
        "from": from_code,
        "to": to_code,
        "amount": amount,
        "rate": rate,
        "result": result,
    }
