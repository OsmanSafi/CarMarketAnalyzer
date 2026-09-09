import os

import httpx
from dotenv import load_dotenv

from app.models.vehicle import ComparableListing

load_dotenv()

AUTO_DEV_API_KEY = os.getenv("AUTO_DEV_API_KEY")
AUTO_DEV_URL = "https://api.auto.dev/listings"


def is_configured() -> bool:
    return bool(AUTO_DEV_API_KEY)


async def search_listings(
    year: int,
    make: str,
    model: str,
    mileage: int,
    zip_code: str,
    trim: str | None = None,
) -> list[ComparableListing]:

    if not AUTO_DEV_API_KEY:
        return []

    # Search adjacent model years.
    # Exact year is still favored later
    # by the comparable scoring engine.
    minimum_year = max(1981, year - 1)
    maximum_year = year + 1

    mileage_variance = max(
        25000,
        int(mileage * 0.40),
    )

    minimum_mileage = max(
        0,
        mileage - mileage_variance,
    )

    maximum_mileage = mileage + mileage_variance

    params = {
        "vehicle.year": (f"{minimum_year}-{maximum_year}"),
        "vehicle.make": make,
        "vehicle.model": model,
        "retailListing.miles": (f"{minimum_mileage}-{maximum_mileage}"),
        "retailListing.used": "true",
        "zip": zip_code,
        "distance": 250,
        "limit": 100,
    }

    # Auto.dev supports exact trim filtering.
    # Keep this strict because these are our
    # highest-value comparable vehicles.
    if trim:
        params["vehicle.trim"] = trim

    headers = {"Authorization": (f"Bearer {AUTO_DEV_API_KEY}")}

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            AUTO_DEV_URL,
            params=params,
            headers=headers,
        )

    if response.status_code != 200:
        return []

    data = response.json()

    return normalize_listings(data.get("data", []))


def safe_string(value) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        return value or None

    if isinstance(value, (int, float)):
        return str(value)

    return None


def safe_int(value) -> int | None:
    if value is None:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def safe_float(value) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_listings(
    raw_listings: list[dict],
) -> list[ComparableListing]:

    normalized = []

    for listing in raw_listings:
        if not isinstance(listing, dict):
            continue

        vehicle = listing.get("vehicle") or {}

        retail = listing.get("retailListing") or {}

        price = safe_float(retail.get("price"))

        if not price or price <= 0:
            continue

        vin = safe_string(vehicle.get("vin") or listing.get("vin"))

        if vin:
            vin = vin.upper()

        dealer = retail.get("dealer")

        if isinstance(dealer, dict):
            dealer = dealer.get("name") or dealer.get("dealerName")

        normalized.append(
            ComparableListing(
                provider="Auto.dev",
                source_site=None,
                vin=vin,
                year=safe_int(vehicle.get("year")),
                make=safe_string(vehicle.get("make")),
                model=safe_string(vehicle.get("model")),
                trim=safe_string(vehicle.get("trim")),
                price=price,
                mileage=safe_int(retail.get("miles")),
                dealer=safe_string(dealer),
                city=safe_string(retail.get("city")),
                state=safe_string(retail.get("state")),
                listing_url=safe_string(retail.get("vdp")),
            )
        )

    return normalized
