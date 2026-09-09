import math
import re
from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median

from app.models.vehicle import ComparableListing


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)

    return " ".join(value.split())


def normalize_trim(value: str | None) -> str:
    value = normalize_text(value)

    aliases = {
        "sporttouring": "sport touring",
        "sport touring": "sport touring",
        "ext": "ex t",
        "ex t": "ex t",
        "exl": "ex l",
        "ex l": "ex l",
        "lxp": "lx p",
        "lx p": "lx p",
    }

    compact = value.replace(" ", "")

    return aliases.get(
        compact,
        aliases.get(value, value),
    )


# ---------------------------------------------------------
# DATA QUALITY
# ---------------------------------------------------------


def basic_listing_is_valid(
    listing: ComparableListing,
) -> bool:
    current_year = datetime.now(timezone.utc).year

    if listing.price is None:
        return False

    # Extremely low marketplace prices are usually
    # bad feeds, deposits, payments, or data errors.
    if listing.price < 1000:
        return False

    if listing.price > 300000:
        return False

    if listing.year is not None and not (1981 <= listing.year <= current_year + 1):
        return False

    return listing.mileage is None or 0 <= listing.mileage <= 400000


def filter_suspicious_listings(
    listings: list[ComparableListing],
) -> tuple[
    list[ComparableListing],
    int,
]:
    valid = [listing for listing in listings if basic_listing_is_valid(listing)]

    # If we have enough data, also use the
    # market itself to detect obviously broken
    # prices.
    if len(valid) >= 10:
        prices = [listing.price for listing in valid]

        market_median = median(prices)

        lower_bound = max(
            1000,
            market_median * 0.25,
        )

        upper_bound = min(
            300000,
            market_median * 4,
        )

        valid = [
            listing
            for listing in valid
            if (lower_bound <= listing.price <= upper_bound)
        ]

    removed = len(listings) - len(valid)

    return valid, removed


# ---------------------------------------------------------
# COMPARABLE SCORING
# ---------------------------------------------------------


def trim_match_score(
    subject_trim: str | None,
    listing_trim: str | None,
) -> tuple[int, str]:
    subject = normalize_trim(subject_trim)

    listing = normalize_trim(listing_trim)

    if not subject:
        return (
            0,
            "subject trim unavailable",
        )

    if not listing:
        return (
            -5,
            "listing trim unavailable",
        )

    if subject == listing:
        return 45, "exact trim"

    subject_tokens = set(subject.split())

    listing_tokens = set(listing.split())

    overlap = subject_tokens & listing_tokens

    if not overlap:
        return (
            -20,
            "different trim",
        )

    similarity = len(overlap) / max(
        len(subject_tokens),
        len(listing_tokens),
    )

    if similarity >= 0.75:
        return (
            30,
            "very similar trim",
        )

    if similarity >= 0.50:
        return (
            18,
            "related trim",
        )

    if "sport" in overlap:
        return (
            12,
            "same sport trim family",
        )

    return (
        -8,
        "weak trim match",
    )


def mileage_match_score(
    target_mileage: int,
    listing_mileage: int | None,
) -> tuple[int, str]:
    if listing_mileage is None:
        return (
            -5,
            "mileage unavailable",
        )

    difference = abs(target_mileage - listing_mileage)

    if difference <= 5000:
        return (
            25,
            "mileage within 5k",
        )

    if difference <= 10000:
        return (
            22,
            "mileage within 10k",
        )

    if difference <= 20000:
        return (
            17,
            "mileage within 20k",
        )

    if difference <= 30000:
        return (
            11,
            "mileage within 30k",
        )

    if difference <= 50000:
        return (
            5,
            "mileage within 50k",
        )

    return (
        -10,
        "large mileage difference",
    )


def year_match_score(
    subject_year: int,
    listing_year: int | None,
) -> tuple[int, str]:
    if listing_year is None:
        return (
            -5,
            "year unavailable",
        )

    difference = abs(subject_year - listing_year)

    if difference == 0:
        return (
            20,
            "exact year",
        )

    if difference == 1:
        return (
            12,
            "year within 1",
        )

    if difference == 2:
        return (
            5,
            "year within 2",
        )

    return (
        -10,
        "large year difference",
    )


def provider_score(
    provider: str,
) -> tuple[int, str]:
    if provider == "Auto.dev":
        return (
            10,
            "local market provider",
        )

    if provider == "Vehicles.dev":
        return (
            3,
            "national market provider",
        )

    return (
        0,
        "market provider",
    )


def quality_score(
    listing: ComparableListing,
) -> tuple[int, str]:
    if listing.data_quality is None:
        return 0, ""

    if listing.data_quality >= 0.90:
        return (
            5,
            "high data quality",
        )

    if listing.data_quality >= 0.75:
        return (
            2,
            "good data quality",
        )

    return (
        -3,
        "lower data quality",
    )


def calculate_comparable_score(
    listing: ComparableListing,
    subject_year: int,
    subject_trim: str | None,
    target_mileage: int,
) -> tuple[int, list[str]]:
    score = 0
    reasons = []

    checks = [
        trim_match_score(
            subject_trim,
            listing.trim,
        ),
        mileage_match_score(
            target_mileage,
            listing.mileage,
        ),
        year_match_score(
            subject_year,
            listing.year,
        ),
        provider_score(
            listing.provider,
        ),
        quality_score(
            listing,
        ),
    ]

    for points, reason in checks:
        score += points

        if reason:
            reasons.append(f"{reason} ({points:+d})")

    score = max(
        0,
        min(
            100,
            score,
        ),
    )

    return score, reasons


def score_comparables(
    listings: list[ComparableListing],
    subject_year: int,
    subject_trim: str | None,
    target_mileage: int,
    subject_vin: str | None = None,
) -> list[dict]:
    results = []

    normalized_subject_vin = subject_vin.strip().upper() if subject_vin else None

    for listing in listings:
        if (
            normalized_subject_vin
            and listing.vin
            and (listing.vin.strip().upper() == normalized_subject_vin)
        ):
            continue

        score, reasons = calculate_comparable_score(
            listing=listing,
            subject_year=subject_year,
            subject_trim=subject_trim,
            target_mileage=(target_mileage),
        )

        results.append(
            {
                "listing": listing,
                "score": score,
                "reasons": reasons,
            }
        )

    return sorted(
        results,
        key=lambda item: item["score"],
        reverse=True,
    )


def select_best_comparables(
    scored: list[dict],
) -> tuple[list[dict], str]:
    strong = [item for item in scored if item["score"] >= 75]

    good = [item for item in scored if (60 <= item["score"] < 75)]

    acceptable = [item for item in scored if (45 <= item["score"] < 60)]

    if len(strong) >= 3:
        return (
            strong[:20],
            "strong_comparables",
        )

    strong_and_good = strong + good

    if len(strong_and_good) >= 5:
        return (
            strong_and_good[:20],
            "strong_and_good_comparables",
        )

    broader = strong + good + acceptable

    if len(broader) >= 5:
        return (
            broader[:20],
            "broadened_comparables",
        )

    if broader:
        return (
            broader[:10],
            "limited_acceptable_comparables",
        )

    return (
        [],
        "no_relevant_comparables",
    )


# ---------------------------------------------------------
# OUTLIERS / WEIGHTING
# ---------------------------------------------------------


def remove_price_outliers(
    scored: list[dict],
) -> list[dict]:
    if len(scored) < 7:
        return scored

    prices = sorted(item["listing"].price for item in scored)

    midpoint = len(prices) // 2

    lower_half = prices[:midpoint]

    if len(prices) % 2 == 0:
        upper_half = prices[midpoint:]
    else:
        upper_half = prices[midpoint + 1 :]

    q1 = median(lower_half)
    q3 = median(upper_half)

    iqr = q3 - q1

    lower_bound = q1 - 1.5 * iqr

    upper_bound = q3 + 1.5 * iqr

    return [
        item for item in scored if (lower_bound <= item["listing"].price <= upper_bound)
    ]


def get_listing_weight(
    item: dict,
    provider_counts: Counter,
) -> float:
    score = max(
        item["score"],
        1,
    )

    provider = item["listing"].provider

    provider_count = provider_counts[provider]

    quality_weight = (score / 100) ** 2

    provider_balance = 1 / math.sqrt(provider_count)

    return quality_weight * provider_balance


def weighted_average_price(
    scored: list[dict],
) -> float:
    provider_counts = Counter(item["listing"].provider for item in scored)

    weighted_total = 0.0
    total_weight = 0.0

    for item in scored:
        weight = get_listing_weight(
            item,
            provider_counts,
        )

        weighted_total += item["listing"].price * weight

        total_weight += weight

    if total_weight == 0:
        return mean(item["listing"].price for item in scored)

    return weighted_total / total_weight


def weighted_median_price(
    scored: list[dict],
) -> float:
    provider_counts = Counter(item["listing"].provider for item in scored)

    weighted = []

    for item in scored:
        weight = get_listing_weight(
            item,
            provider_counts,
        )

        weighted.append(
            (
                item["listing"].price,
                weight,
            )
        )

    weighted.sort(key=lambda item: item[0])

    total_weight = sum(weight for _, weight in weighted)

    halfway = total_weight / 2

    running = 0.0

    for price, weight in weighted:
        running += weight

        if running >= halfway:
            return price

    return weighted[-1][0]


def percentile_price(
    prices: list[float],
    percentile: float,
) -> float:
    ordered = sorted(prices)

    index = round((len(ordered) - 1) * percentile)

    return ordered[index]


# ---------------------------------------------------------
# CONFIDENCE
# ---------------------------------------------------------


def determine_confidence(
    selected: list[dict],
    strategy: str,
) -> str:
    if not selected:
        return "low"

    strong_count = sum(1 for item in selected if item["score"] >= 75)

    providers = {item["listing"].provider for item in selected}

    if len(selected) >= 8 and strong_count >= 3 and len(providers) >= 2:
        return "high"

    if (
        len(selected) >= 5
        and max(item["score"] for item in selected) >= 65
        and strategy != "no_relevant_comparables"
    ):
        return "medium"

    return "low"


# ---------------------------------------------------------
# TRADE VALUE MODEL
# ---------------------------------------------------------


def get_reconditioning_reserve(
    mileage: int,
) -> float:
    if mileage < 30000:
        return 500

    if mileage < 60000:
        return 650

    if mileage < 90000:
        return 850

    if mileage < 120000:
        return 1100

    if mileage < 160000:
        return 1400

    return 1800


def estimate_trade_value(
    retail_value: float,
    mileage: int,
    subject_year: int,
    confidence: str,
) -> dict:
    current_year = datetime.now(timezone.utc).year

    vehicle_age = max(
        0,
        current_year - subject_year,
    )

    dealer_margin_reserve = max(
        1500,
        retail_value * 0.08,
    )

    reconditioning_reserve = get_reconditioning_reserve(mileage)

    # Small reserve for older vehicles,
    # reflecting increasing dealer risk.
    age_reserve = min(
        750,
        max(
            0,
            vehicle_age - 5,
        )
        * 100,
    )

    trade_midpoint = max(
        0,
        (retail_value - dealer_margin_reserve - reconditioning_reserve - age_reserve),
    )

    uncertainty_percentages = {
        "high": 0.04,
        "medium": 0.05,
        "low": 0.08,
    }

    uncertainty_percentage = uncertainty_percentages.get(
        confidence,
        0.08,
    )

    uncertainty = max(
        750,
        retail_value * uncertainty_percentage,
    )

    trade_low = max(
        0,
        trade_midpoint - uncertainty,
    )

    trade_high = max(
        trade_low,
        trade_midpoint + uncertainty,
    )

    return {
        "low": round(
            trade_low,
            2,
        ),
        "high": round(
            trade_high,
            2,
        ),
        "midpoint": round(
            trade_midpoint,
            2,
        ),
        "components": {
            "retail_anchor": round(
                retail_value,
                2,
            ),
            "dealer_margin_reserve": round(
                dealer_margin_reserve,
                2,
            ),
            "reconditioning_reserve": round(
                reconditioning_reserve,
                2,
            ),
            "age_reserve": round(
                age_reserve,
                2,
            ),
            "uncertainty_band": round(
                uncertainty,
                2,
            ),
        },
    }


# ---------------------------------------------------------
# MAIN ANALYSIS
# ---------------------------------------------------------


def analyze_market(
    listings: list[ComparableListing],
    target_mileage: int,
    subject_year: int,
    subject_trim: str | None = None,
    subject_vin: str | None = None,
) -> dict:
    if not listings:
        return empty_analysis()

    raw_listing_count = len(listings)

    (
        validated_listings,
        invalid_removed,
    ) = filter_suspicious_listings(listings)

    if not validated_listings:
        return empty_analysis(
            warning=("All returned listings failed basic market data validation.")
        )

    scored = score_comparables(
        listings=validated_listings,
        subject_year=subject_year,
        subject_trim=subject_trim,
        target_mileage=(target_mileage),
        subject_vin=subject_vin,
    )

    if not scored:
        return empty_analysis(
            warning=(
                "No comparable listings remained after excluding the subject vehicle."
            )
        )

    selected, strategy = select_best_comparables(scored)

    if not selected:
        return empty_analysis(
            warning=(
                "Listings were found, but "
                "none were sufficiently "
                "similar to produce a "
                "reliable valuation."
            )
        )

    before_outlier_removal = len(selected)

    selected = remove_price_outliers(selected)

    if not selected:
        return empty_analysis()

    weighted_average = weighted_average_price(selected)

    weighted_median = weighted_median_price(selected)

    estimated_market_value = weighted_median * 0.70 + weighted_average * 0.30

    prices = [item["listing"].price for item in selected]

    typical_low = percentile_price(
        prices,
        0.25,
    )

    typical_high = percentile_price(
        prices,
        0.75,
    )

    provider_groups = {}

    for item in selected:
        provider = item["listing"].provider

        provider_groups.setdefault(
            provider,
            [],
        ).append(item["listing"].price)

    provider_estimates = {
        provider: round(
            median(provider_prices),
            2,
        )
        for (
            provider,
            provider_prices,
        ) in provider_groups.items()
    }

    confidence = determine_confidence(
        selected,
        strategy,
    )

    purchase_low = estimated_market_value * 0.97

    purchase_high = estimated_market_value * 1.02

    trade_value = estimate_trade_value(
        retail_value=(estimated_market_value),
        mileage=target_mileage,
        subject_year=(subject_year),
        confidence=confidence,
    )

    top_comparables = []

    for item in selected[:10]:
        listing = item["listing"]

        top_comparables.append(
            {
                "score": item["score"],
                "provider": (listing.provider),
                "vin": listing.vin,
                "year": listing.year,
                "make": listing.make,
                "model": listing.model,
                "trim": listing.trim,
                "price": listing.price,
                "mileage": (listing.mileage),
                "city": listing.city,
                "state": (listing.state),
                "listing_url": (listing.listing_url),
                "match_reasons": (item["reasons"]),
            }
        )

    warning = None

    if confidence == "low":
        warning = (
            "The available listings do not "
            "include enough high-quality "
            "comparable vehicles. Treat "
            "this valuation as preliminary."
        )

    return {
        "raw_listing_count": (raw_listing_count),
        "validated_listing_count": (len(validated_listings)),
        "invalid_listings_removed": (invalid_removed),
        "subject_vin_excluded": (subject_vin is not None),
        "candidate_comparable_count": (len(scored)),
        "selected_comparable_count": (len(selected)),
        "outliers_removed": (before_outlier_removal - len(selected)),
        "selection_strategy": (strategy),
        "providers_used": len(provider_groups),
        "provider_estimates": (provider_estimates),
        "weighted_average_price": round(
            weighted_average,
            2,
        ),
        "weighted_median_price": round(
            weighted_median,
            2,
        ),
        "estimated_market_value": round(
            estimated_market_value,
            2,
        ),
        "typical_listing_range": {
            "low": round(
                typical_low,
                2,
            ),
            "high": round(
                typical_high,
                2,
            ),
        },
        "fair_purchase_range": {
            "low": round(
                purchase_low,
                2,
            ),
            "high": round(
                purchase_high,
                2,
            ),
        },
        "estimated_trade_range": {
            "low": (trade_value["low"]),
            "high": (trade_value["high"]),
            "midpoint": (trade_value["midpoint"]),
        },
        "trade_value_method": ("retail_less_modeled_dealer_costs"),
        "trade_value_components": (trade_value["components"]),
        "target_mileage": (target_mileage),
        "confidence": confidence,
        "warning": warning,
        "top_comparables": (top_comparables),
    }


def empty_analysis(
    warning: str | None = None,
) -> dict:
    return {
        "raw_listing_count": 0,
        "validated_listing_count": 0,
        "invalid_listings_removed": 0,
        "candidate_comparable_count": 0,
        "selected_comparable_count": 0,
        "estimated_market_value": None,
        "fair_purchase_range": None,
        "estimated_trade_range": None,
        "provider_estimates": {},
        "confidence": "low",
        "warning": (warning or ("No usable comparable vehicles were found.")),
        "top_comparables": [],
    }
