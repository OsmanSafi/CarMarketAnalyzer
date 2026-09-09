import asyncio

from app.models.vehicle import (
    ComparableListing,
)
from app.services import (
    auto_dev_service,
)
from app.services import (
    vehicles_dev_service,
)


async def get_market_listings(
    year: int,
    make: str,
    model: str,
    mileage: int,
    zip_code: str,
    trim: str | None = None,
) -> dict:

    providers = []

    if auto_dev_service.is_configured():
        providers.append(
            (
                "Auto.dev",
                auto_dev_service.search_listings(
                    year=year,
                    make=make,
                    model=model,
                    trim=trim,
                    mileage=mileage,
                    zip_code=zip_code,
                ),
            )
        )

    if vehicles_dev_service.is_configured():
        providers.append(
            (
                "Vehicles.dev",
                vehicles_dev_service.search_listings(
                    year=year,
                    make=make,
                    model=model,
                    trim=trim,
                    mileage=mileage,
                    zip_code=zip_code,
                ),
            )
        )

    results = await asyncio.gather(
        *[request for _, request in providers],
        return_exceptions=True,
    )

    combined = []

    provider_counts = {}
    provider_status = {}

    for (
        provider,
        _,
    ), result in zip(
        providers,
        results,
    ):
        if isinstance(
            result,
            Exception,
        ):
            provider_counts[provider] = 0

            provider_status[provider] = "error"

            continue

        provider_counts[provider] = len(result)

        provider_status[provider] = "success"

        combined.extend(result)

    before = len(combined)

    listings = deduplicate_listings(combined)

    return {
        "listings": listings,
        "provider_counts": (provider_counts),
        "provider_status": (provider_status),
        "before_deduplication": before,
        "after_deduplication": len(listings),
    }


def deduplicate_listings(
    listings: list[ComparableListing],
) -> list[ComparableListing]:

    results = []

    seen_vins = set()
    seen_fallbacks = set()

    for listing in listings:
        if listing.vin:
            vin = listing.vin.strip().upper()

            if vin in seen_vins:
                continue

            seen_vins.add(vin)

        else:
            fallback = (
                listing.year,
                (listing.make or "").lower(),
                (listing.model or "").lower(),
                round(listing.price),
                listing.mileage,
                (listing.dealer or "").lower(),
            )

            if fallback in seen_fallbacks:
                continue

            seen_fallbacks.add(fallback)

        results.append(listing)

    return results
