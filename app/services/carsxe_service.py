import os

import httpx
from dotenv import load_dotenv

load_dotenv()

CARSXE_API_KEY = os.getenv("CARSXE_API_KEY")

CARSXE_MARKET_VALUE_URL = "https://api.carsxe.com/v2/marketvalue"


def adjusted_value(
    bucket: dict | None,
    field: str,
) -> float | None:
    if not bucket:
        return None

    value = bucket.get(field)

    if isinstance(value, (int, float)):
        return float(value)

    return None


async def get_carsxe_market_value(
    vin: str,
    mileage: int,
    state: str | None = None,
) -> dict:
    if not CARSXE_API_KEY:
        return {
            "status": "not_configured",
            "wholesale": {},
            "retail": {},
        }

    params = {
        "key": CARSXE_API_KEY,
        "vin": vin,
        "mileage": mileage,
    }

    if state:
        params["state"] = state.upper()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                CARSXE_MARKET_VALUE_URL,
                params=params,
                headers={"Accept": "application/json"},
            )

            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as exc:
        return {
            "status": "http_error",
            "status_code": (exc.response.status_code),
            "wholesale": {},
            "retail": {},
            "error": exc.response.text,
        }

    except Exception as exc:
        return {
            "status": "error",
            "wholesale": {},
            "retail": {},
            "error": str(exc),
        }

    wholesale_details = {
        "excellent": data.get("whole_xclean"),
        "clean": data.get("whole_clean"),
        "average": data.get("whole_avg"),
        "rough": data.get("whole_rough"),
    }

    retail_details = {
        "excellent": data.get("retail_xclean"),
        "clean": data.get("retail_clean"),
        "average": data.get("retail_avg"),
        "rough": data.get("retail_rough"),
    }

    wholesale = {
        "excellent": adjusted_value(
            wholesale_details["excellent"],
            "adjusted_whole_xclean",
        ),
        "clean": adjusted_value(
            wholesale_details["clean"],
            "adjusted_whole_clean",
        ),
        "average": adjusted_value(
            wholesale_details["average"],
            "adjusted_whole_avg",
        ),
        "rough": adjusted_value(
            wholesale_details["rough"],
            "adjusted_whole_rough",
        ),
    }

    retail = {
        "excellent": adjusted_value(
            retail_details["excellent"],
            "adjusted_retail_xclean",
        ),
        "clean": adjusted_value(
            retail_details["clean"],
            "adjusted_retail_clean",
        ),
        "average": adjusted_value(
            retail_details["average"],
            "adjusted_retail_avg",
        ),
        "rough": adjusted_value(
            retail_details["rough"],
            "adjusted_retail_rough",
        ),
    }

    return {
        "status": "success",
        "publish_date": data.get("publish_date"),
        "state": data.get("state"),
        "vehicle": {
            "year": data.get("model_year"),
            "make": data.get("make"),
            "model": data.get("model"),
            "series": data.get("series"),
            "style": data.get("style"),
            "class_name": data.get("class_name"),
        },
        "wholesale": wholesale,
        "retail": retail,
        "wholesale_details": (wholesale_details),
        "retail_details": retail_details,
    }
