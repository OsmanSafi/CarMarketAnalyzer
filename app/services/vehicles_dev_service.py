import os

import httpx
from dotenv import load_dotenv

from app.models.vehicle import ComparableListing

load_dotenv()

VEHICLES_DEV_API_KEY = os.getenv("VEHICLES_DEV_API_KEY") or os.getenv(
    "VEHICLES_API_KEY"
)

VEHICLES_DEV_URL = "https://api.vehicles.dev/v1/vehicles/listings"


def is_configured() -> bool:
    return bool(VEHICLES_DEV_API_KEY)


def canonical_make(make: str) -> str:
    special_makes = {
        "BMW": "BMW",
        "GMC": "GMC",
        "MINI": "MINI",
        "RAM": "Ram",
        "FIAT": "Fiat",
        "KIA": "Kia",
        "HONDA": "Honda",
        "TOYOTA": "Toyota",
        "TESLA": "Tesla",
        "ACURA": "Acura",
        "LEXUS": "Lexus",
        "FORD": "Ford",
        "CHEVROLET": "Chevrolet",
        "NISSAN": "Nissan",
        "HYUNDAI": "Hyundai",
        "SUBARU": "Subaru",
        "MAZDA": "Mazda",
        "VOLKSWAGEN": "Volkswagen",
        "MERCEDES-BENZ": "Mercedes-Benz",
    }

    clean = make.strip()

    return special_makes.get(
        clean.upper(),
        clean.title(),
    )


def canonical_model(model: str) -> str:
    clean = model.strip()

    if "-" in clean:
        parts = clean.split("-")

        formatted = []

        for part in parts:
            if len(part) <= 3:
                formatted.append(part.upper())
            else:
                formatted.append(part.title())

        return "-".join(formatted)

    return clean.title()


async def search_listings(
    year: int,
    make: str,
    model: str,
    mileage: int,
    zip_code: str,
    trim: str | None = None,
) -> list[ComparableListing]:

    if not VEHICLES_DEV_API_KEY:
        return []

    minimum_year = max(
        1981,
        year - 1,
    )

    maximum_year = year + 1

    mileage_variance = max(
        30000,
        int(mileage * 0.45),
    )

    maximum_mileage = mileage + mileage_variance

    params = {
        "make": canonical_make(make),
        "model": canonical_model(model),
        "year_min": minimum_year,
        "year_max": maximum_year,
        "mileage_max": maximum_mileage,
        "condition": "used",
        "active": "true",
        "valid_vin": "true",
        "min_quality": 0.70,
        "limit": 200,
    }

    headers = {
        "Authorization": (f"Bearer {VEHICLES_DEV_API_KEY}"),
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            VEHICLES_DEV_URL,
            params=params,
            headers=headers,
        )

    if response.status_code != 200:
        return []

    data = response.json()

    return normalize_listings(data.get("results", []))


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

        price = safe_float(listing.get("price"))

        if not price or price <= 0:
            continue

        vin = safe_string(listing.get("vin"))

        if vin:
            vin = vin.upper()

        normalized.append(
            ComparableListing(
                provider="Vehicles.dev",
                source_site=safe_string(listing.get("source")),
                vin=vin,
                year=safe_int(listing.get("year")),
                make=safe_string(listing.get("make")),
                model=safe_string(listing.get("model")),
                trim=safe_string(listing.get("trim")),
                price=price,
                mileage=safe_int(listing.get("miles")),
                dealer=safe_string(listing.get("dealer_name")),
                city=safe_string(listing.get("city")),
                state=safe_string(listing.get("state")),
                days_on_market=safe_int(listing.get("days_on_market")),
                data_quality=safe_float(listing.get("data_quality")),
                listing_url=safe_string(listing.get("vdp_url")),
            )
        )

    return normalized
