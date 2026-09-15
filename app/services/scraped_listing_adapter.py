import re

from app.models.vehicle import ComparableListing
from app.services.generic_dealer_scraper import (
    ScrapedListing,
)
from app.services.pricing_service import normalize_trim


CONDITION_WORDS = {
    "used",
    "pre-owned",
    "preowned",
    "certified",
    "cpo",
}


def clean_text(
    value: str | None,
) -> str | None:
    if not value:
        return None

    cleaned = " ".join(value.strip().split())

    return cleaned or None


def infer_trim_from_title(
    listing: ScrapedListing,
) -> str | None:
    """
    Infer trim generically from a listing title.

    Example:

    Used 2024 Acura Integra w/A-Spec Package

    Known:
        year = 2024
        make = Acura
        model = Integra

    Remaining:
        w/A-Spec Package

    normalize_trim() then converts that
    to our canonical internal trim.
    """

    if not listing.title:
        return listing.trim

    title = listing.title.strip()

    # Remove common listing-condition words.
    for word in CONDITION_WORDS:
        title = re.sub(
            rf"\b{re.escape(word)}\b",
            " ",
            title,
            flags=re.IGNORECASE,
        )

    if listing.year:
        title = re.sub(
            rf"\b{listing.year}\b",
            " ",
            title,
            flags=re.IGNORECASE,
        )

    # Remove the exact make returned by
    # structured listing data.
    if listing.make:
        title = re.sub(
            re.escape(listing.make),
            " ",
            title,
            count=1,
            flags=re.IGNORECASE,
        )

    # Remove the exact model returned by
    # structured listing data.
    #
    # This works for multi-word models such
    # as:
    #   Grand Cherokee WK
    #   Hardtop 2 Door
    #   Civic Sedan
    if listing.model:
        title = re.sub(
            re.escape(listing.model),
            " ",
            title,
            count=1,
            flags=re.IGNORECASE,
        )

    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip(" -|:,")

    if not title:
        return None

    normalized = normalize_trim(title)

    return normalized or None


def convert_scraped_listing(
    listing: ScrapedListing,
    default_city: str | None = None,
    default_state: str | None = None,
    default_dealer: str | None = None,
) -> ComparableListing | None:
    """
    Convert generic scraped dealer data into
    the application's standard ComparableListing.
    """

    if listing.price is None:
        return None

    if listing.year is None:
        return None

    if not listing.make:
        return None

    if not listing.model:
        return None

    trim = listing.trim

    if not trim:
        trim = infer_trim_from_title(listing)
    else:
        trim = normalize_trim(trim)

    return ComparableListing(
        provider="Dealer Website",
        source_site=listing.source_site,
        vin=listing.vin,
        year=listing.year,
        make=clean_text(listing.make),
        model=clean_text(listing.model),
        trim=trim,
        price=listing.price,
        mileage=listing.mileage,
        dealer=(listing.dealer or default_dealer),
        city=(listing.city or default_city),
        state=(listing.state or default_state),
        days_on_market=None,
        data_quality=listing.data_quality,
        listing_url=listing.page_url,
    )


def convert_scraped_listings(
    listings: list[ScrapedListing],
    default_city: str | None = None,
    default_state: str | None = None,
    default_dealer: str | None = None,
) -> list[ComparableListing]:
    converted = []

    for listing in listings:
        comparable = convert_scraped_listing(
            listing=listing,
            default_city=default_city,
            default_state=default_state,
            default_dealer=default_dealer,
        )

        if comparable:
            converted.append(comparable)

    return converted
