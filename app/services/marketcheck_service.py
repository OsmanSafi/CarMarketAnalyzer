import os

import httpx
from dotenv import load_dotenv

load_dotenv()

MARKETCHECK_API_KEY = os.getenv("MARKETCHECK_API_KEY")

MARKETCHECK_BASE_URL = "https://api.marketcheck.com/v2"


async def get_marketcheck_price(
    vin: str,
    mileage: int,
    zip_code: str,
    dealer_type: str = "franchise",
) -> dict:
    if not MARKETCHECK_API_KEY:
        return {
            "status": "not_configured",
            "marketcheck_price": None,
            "msrp": None,
            "raw": None,
        }

    url = f"{MARKETCHECK_BASE_URL}/predict/car/us/marketcheck_price"

    params = {
        "api_key": MARKETCHECK_API_KEY,
        "vin": vin,
        "miles": mileage,
        "zip": zip_code,
        "dealer_type": dealer_type,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
            )

            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as exc:
        return {
            "status": "http_error",
            "status_code": exc.response.status_code,
            "marketcheck_price": None,
            "msrp": None,
            "raw": exc.response.text,
        }

    except Exception as exc:
        return {
            "status": "error",
            "marketcheck_price": None,
            "msrp": None,
            "error": str(exc),
            "raw": None,
        }

    return {
        "status": "success",
        "marketcheck_price": data.get("marketcheck_price"),
        "msrp": data.get("msrp"),
        "raw": data,
    }
