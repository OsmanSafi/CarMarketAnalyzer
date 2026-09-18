import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, median

from app.models.vehicle import ComparableListing

MIN_TRIM_SAMPLE = 3


# ---------------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------------


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    value = value.lower().strip()
    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(value.split())


def normalize_trim(
    value: str | None,
) -> str:
    value = normalize_text(value)

    if not value:
        return ""

    tokens = value.split()

    # Words that commonly appear in
    # listing-provider trim descriptions
    # but do not change the trim itself.
    removable_tokens = {
        "w",
        "with",
        "package",
        "pkg",
    }

    # Generic terminology normalization.
    token_aliases = {
        "technology": "tech",
        "navigation": "navi",
        "automatic": "auto",
    }

    cleaned_tokens = []

    for token in tokens:
        if token in removable_tokens:
            continue

        token = token_aliases.get(
            token,
            token,
        )

        cleaned_tokens.append(token)

    if not cleaned_tokens:
        return ""

    # Remove duplicates while retaining
    # meaningful trim components.
    unique_tokens = []

    for token in cleaned_tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)

    # Sort only for canonical comparison.
    # This lets provider naming differences
    # such as:
    #
    # "A-SPEC Tech"
    # "Tech A-SPEC"
    #
    # resolve to the same internal trim.
    return " ".join(sorted(unique_tokens))


def robust_median(
    values: list[float],
) -> float:
    if not values:
        return 0.0

    center = median(values)

    if len(values) < 5:
        return float(center)

    deviations = [abs(value - center) for value in values]

    mad = median(deviations)

    if mad == 0:
        return float(center)

    filtered = [value for value in values if (abs(value - center) <= 3 * mad)]

    if not filtered:
        return float(center)

    return float(median(filtered))


# ---------------------------------------------------------
# DATA QUALITY
# ---------------------------------------------------------


def basic_listing_is_valid(
    listing: ComparableListing,
) -> bool:
    current_year = datetime.now(timezone.utc).year

    if listing.price is None:
        return False

    if listing.price < 1000:
        return False

    if listing.price > 300000:
        return False

    if listing.year is not None and not (1981 <= listing.year <= current_year + 1):
        return False

    return listing.mileage is None or (0 <= listing.mileage <= 400000)


def filter_suspicious_listings(
    listings: list[ComparableListing],
) -> tuple[
    list[ComparableListing],
    int,
]:
    valid = [listing for listing in listings if basic_listing_is_valid(listing)]

    if len(valid) >= 10:
        prices = [float(listing.price) for listing in valid]

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
# MARKET-DERIVED MILEAGE / YEAR ADJUSTMENTS
# ---------------------------------------------------------


def estimate_market_adjustment_rates(
    listings: list[ComparableListing],
    subject_trim: str | None,
    subject_year: int,
    target_mileage: int,
    subject_state: (str | None) = None,
) -> tuple[
    float,
    int,
    float,
    int,
]:
    normalized_subject_trim = normalize_trim(subject_trim)

    candidates: list[ComparableListing] = []

    for listing in listings:
        if listing.year is None or listing.mileage is None:
            continue

        if normalized_subject_trim:
            listing_trim = normalize_trim(listing.trim)

            if listing_trim != normalized_subject_trim:
                continue

        if abs(listing.year - subject_year) > 2:
            continue

        if abs(listing.mileage - target_mileage) > 60000:
            continue

        candidates.append(listing)

    # Prefer listings in the
    # subject's own state when we
    # still have enough observations.
    if subject_state:
        state_candidates = [
            listing
            for listing in candidates
            if (
                listing.state
                and (listing.state.strip().upper() == subject_state.strip().upper())
            )
        ]

        if len(state_candidates) >= 6:
            candidates = state_candidates

    # Regression becomes unstable
    # with too few observations.
    if len(candidates) < 6:
        return (
            0.0,
            len(candidates),
            0.0,
            len(candidates),
        )

    prices = [float(listing.price) for listing in candidates]

    price_center = median(prices)

    deviations = [abs(price - price_center) for price in prices]

    mad = median(deviations)

    # Remove extreme same-trim
    # asking-price outliers before
    # fitting the regression.
    if mad > 0:
        filtered = [
            listing
            for listing in candidates
            if (abs(float(listing.price) - price_center) <= 3 * mad)
        ]

        if len(filtered) >= 6:
            candidates = filtered

    mileages = [listing.mileage / 1000 for listing in candidates]

    years = [float(listing.year) for listing in candidates]

    values = [float(listing.price) for listing in candidates]

    mileage_mean = mean(mileages)

    year_mean = mean(years)

    value_mean = mean(values)

    mileage_centered = [value - mileage_mean for value in mileages]

    year_centered = [value - year_mean for value in years]

    price_centered = [value - value_mean for value in values]

    mileage_variance = sum(value * value for value in mileage_centered)

    year_variance = sum(value * value for value in year_centered)

    cross_variance = sum(
        mileage_value * year_value
        for (
            mileage_value,
            year_value,
        ) in zip(
            mileage_centered,
            year_centered,
            strict=False,
        )
    )

    mileage_price_covariance = sum(
        mileage_value * price_value
        for (
            mileage_value,
            price_value,
        ) in zip(
            mileage_centered,
            price_centered,
            strict=False,
        )
    )

    year_price_covariance = sum(
        year_value * price_value
        for (
            year_value,
            price_value,
        ) in zip(
            year_centered,
            price_centered,
            strict=False,
        )
    )

    determinant = mileage_variance * year_variance - cross_variance**2

    if abs(determinant) < 0.000001:
        return (
            0.0,
            len(candidates),
            0.0,
            len(candidates),
        )

    mileage_coefficient = (
        (mileage_price_covariance * year_variance)
        - (year_price_covariance * cross_variance)
    ) / determinant

    year_coefficient = (
        (year_price_covariance * mileage_variance)
        - (mileage_price_covariance * cross_variance)
    ) / determinant

    # Mileage coefficient normally
    # comes back negative because
    # higher mileage lowers value.
    mileage_value_per_1000 = max(
        0.0,
        -mileage_coefficient,
    )

    # Newer model years should
    # generally carry more value.
    year_value_per_year = max(
        0.0,
        year_coefficient,
    )

    sample_count = len(candidates)

    return (
        mileage_value_per_1000,
        sample_count,
        year_value_per_year,
        sample_count,
    )


def normalize_for_mileage(
    price: float,
    listing_mileage: (int | None),
    target_mileage: int,
    mileage_rate: float,
) -> float:
    if listing_mileage is None:
        return price

    mileage_difference = target_mileage - listing_mileage

    adjustment = mileage_rate * mileage_difference / 1000

    return price - adjustment


def normalize_for_year(
    price: float,
    listing_year: int | None,
    subject_year: int,
    year_rate: float,
) -> float:
    if listing_year is None:
        return price

    year_difference = subject_year - listing_year

    return price + year_rate * year_difference


# ---------------------------------------------------------
# MARKET-DERIVED TRIM VALUE
# ---------------------------------------------------------


def normalize_to_subject_year_and_mileage(
    listing: ComparableListing,
    subject_year: int,
    target_mileage: int,
    mileage_rate: float,
    year_rate: float,
) -> float:
    value = float(listing.price)

    value = normalize_for_mileage(
        price=value,
        listing_mileage=(listing.mileage),
        target_mileage=(target_mileage),
        mileage_rate=(mileage_rate),
    )

    value = normalize_for_year(
        price=value,
        listing_year=(listing.year),
        subject_year=(subject_year),
        year_rate=(year_rate),
    )

    return value


def estimate_trim_market_levels(
    listings: list[ComparableListing],
    subject_year: int,
    target_mileage: int,
    mileage_rate: float,
    year_rate: float,
) -> tuple[
    dict[str, dict],
    float | None,
]:
    trim_values: dict[
        str,
        list[float],
    ] = defaultdict(list)

    all_values: list[float] = []

    for listing in listings:
        value = normalize_to_subject_year_and_mileage(
            listing=listing,
            subject_year=(subject_year),
            target_mileage=(target_mileage),
            mileage_rate=(mileage_rate),
            year_rate=(year_rate),
        )

        all_values.append(value)

        trim = normalize_trim(listing.trim)

        if trim:
            trim_values[trim].append(value)

    trim_levels: dict[
        str,
        dict,
    ] = {}

    for (
        trim,
        values,
    ) in trim_values.items():
        if len(values) < MIN_TRIM_SAMPLE:
            continue

        trim_levels[trim] = {
            "value": round(
                robust_median(values),
                2,
            ),
            "sample_count": (len(values)),
        }

    model_level = robust_median(all_values) if all_values else None

    return (
        trim_levels,
        model_level,
    )


# ---------------------------------------------------------
# COMPARABLE SCORING
# ---------------------------------------------------------


def trim_match_score(
    subject_trim: str | None,
    listing_trim: str | None,
) -> tuple[
    int,
    str,
]:
    subject = normalize_trim(subject_trim)

    listing = normalize_trim(listing_trim)

    if not subject:
        return (
            0,
            ("subject trim unavailable"),
        )

    if not listing:
        return (
            -5,
            ("listing trim unavailable"),
        )

    if subject == listing:
        return (
            30,
            "exact trim",
        )

    subject_tokens = set(subject.split())

    listing_tokens = set(listing.split())

    overlap = subject_tokens & listing_tokens

    if not overlap:
        return (
            0,
            "different trim",
        )

    similarity = len(overlap) / max(
        len(subject_tokens),
        len(listing_tokens),
    )

    if similarity >= 0.75:
        return (
            18,
            ("very similar trim"),
        )

    if similarity >= 0.50:
        return (
            10,
            "related trim",
        )

    return (
        3,
        ("weak trim relationship"),
    )


def mileage_match_score(
    target_mileage: int,
    listing_mileage: (int | None),
) -> tuple[
    int,
    str,
]:
    if listing_mileage is None:
        return (
            -5,
            ("mileage unavailable"),
        )

    difference = abs(target_mileage - listing_mileage)

    if difference <= 5000:
        return (
            30,
            ("mileage within 5k"),
        )

    if difference <= 10000:
        return (
            26,
            ("mileage within 10k"),
        )

    if difference <= 20000:
        return (
            20,
            ("mileage within 20k"),
        )

    if difference <= 30000:
        return (
            14,
            ("mileage within 30k"),
        )

    if difference <= 50000:
        return (
            7,
            ("mileage within 50k"),
        )

    return (
        -10,
        ("large mileage difference"),
    )


def year_match_score(
    subject_year: int,
    listing_year: (int | None),
) -> tuple[
    int,
    str,
]:
    if listing_year is None:
        return (
            -5,
            "year unavailable",
        )

    difference = abs(subject_year - listing_year)

    if difference == 0:
        return (
            25,
            "exact year",
        )

    if difference == 1:
        return (
            18,
            "year within 1",
        )

    if difference == 2:
        return (
            10,
            "year within 2",
        )

    return (
        -10,
        ("large year difference"),
    )


def geography_score(
    subject_state: (str | None),
    listing_state: (str | None),
) -> tuple[
    int,
    str,
]:
    if not subject_state or not listing_state:
        return (
            0,
            "",
        )

    if subject_state.strip().upper() == listing_state.strip().upper():
        return (
            10,
            "same state",
        )

    return (
        0,
        "different state",
    )


def quality_score(
    listing: ComparableListing,
) -> tuple[
    int,
    str,
]:
    if listing.data_quality is None:
        return (
            0,
            "",
        )

    if listing.data_quality >= 0.90:
        return (
            5,
            ("high data quality"),
        )

    if listing.data_quality >= 0.75:
        return (
            2,
            ("good data quality"),
        )

    return (
        -3,
        ("lower data quality"),
    )


def calculate_comparable_score(
    listing: ComparableListing,
    subject_year: int,
    subject_trim: str | None,
    target_mileage: int,
    subject_state: str | None,
) -> tuple[
    int,
    list[str],
]:
    score = 0

    reasons: list[str] = []

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
        geography_score(
            subject_state,
            listing.state,
        ),
        quality_score(listing),
    ]

    for (
        points,
        reason,
    ) in checks:
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

    return (
        score,
        reasons,
    )


# ---------------------------------------------------------
# DAYS ON MARKET
# ---------------------------------------------------------


def days_on_market_weight(
    days_on_market: (int | None),
) -> float:
    if days_on_market is None or days_on_market < 0:
        return 1.0

    capped_days = min(
        days_on_market,
        180,
    )

    return max(
        0.50,
        (1.0 - capped_days / 360),
    )


# ---------------------------------------------------------
# NORMALIZED COMPARABLES
# ---------------------------------------------------------


def build_normalized_comparables(
    listings: list[ComparableListing],
    subject_year: int,
    subject_trim: str | None,
    target_mileage: int,
    subject_state: str | None,
    subject_vin: str | None,
    mileage_rate: float,
    year_rate: float,
    trim_levels: dict[
        str,
        dict,
    ],
) -> list[dict]:
    results: list[dict] = []

    normalized_subject_vin = subject_vin.strip().upper() if subject_vin else None

    subject_trim_normalized = normalize_trim(subject_trim)

    subject_trim_level = trim_levels.get(
        subject_trim_normalized,
        {},
    ).get("value")

    for listing in listings:
        if (
            normalized_subject_vin
            and listing.vin
            and (listing.vin.strip().upper() == normalized_subject_vin)
        ):
            continue

        (
            score,
            reasons,
        ) = calculate_comparable_score(
            listing=listing,
            subject_year=(subject_year),
            subject_trim=(subject_trim),
            target_mileage=(target_mileage),
            subject_state=(subject_state),
        )

        raw_price = float(listing.price)

        mileage_normalized = normalize_for_mileage(
            price=raw_price,
            listing_mileage=(listing.mileage),
            target_mileage=(target_mileage),
            mileage_rate=(mileage_rate),
        )

        mileage_adjustment = mileage_normalized - raw_price

        year_normalized = normalize_for_year(
            price=(mileage_normalized),
            listing_year=(listing.year),
            subject_year=(subject_year),
            year_rate=(year_rate),
        )

        year_adjustment = year_normalized - mileage_normalized

        listing_trim = normalize_trim(listing.trim)

        listing_trim_level = trim_levels.get(
            listing_trim,
            {},
        ).get("value")

        trim_adjustment = 0.0

        if subject_trim_level is not None and listing_trim_level is not None:
            trim_adjustment = subject_trim_level - listing_trim_level

        adjusted_price = year_normalized + trim_adjustment

        results.append(
            {
                "listing": (listing),
                "score": score,
                "reasons": (reasons),
                "raw_price": (raw_price),
                "adjusted_price": (adjusted_price),
                "adjustments": {
                    "mileage": (mileage_adjustment),
                    "year": (year_adjustment),
                    "trim": (trim_adjustment),
                },
            }
        )

    return sorted(
        results,
        key=lambda item: item["score"],
        reverse=True,
    )


def select_best_comparables(
    scored: list[dict],
) -> tuple[
    list[dict],
    str,
]:
    strong = [item for item in scored if (item["score"] >= 70)]

    good = [item for item in scored if (55 <= item["score"] < 70)]

    acceptable = [item for item in scored if (40 <= item["score"] < 55)]

    if len(strong) >= 5:
        return (
            strong[:20],
            "strong_comparables",
        )

    combined = strong + good

    if len(combined) >= 5:
        return (
            combined[:20],
            ("strong_and_good_comparables"),
        )

    broader = strong + good + acceptable

    if len(broader) >= 5:
        return (
            broader[:20],
            ("broadened_comparables"),
        )

    if broader:
        return (
            broader[:10],
            ("limited_comparables"),
        )

    return (
        [],
        ("no_relevant_comparables"),
    )


# ---------------------------------------------------------
# OUTLIERS
# ---------------------------------------------------------


def remove_price_outliers(
    scored: list[dict],
) -> list[dict]:
    if len(scored) < 7:
        return scored

    prices = sorted(item["adjusted_price"] for item in scored)

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
        item
        for item in scored
        if (lower_bound <= item["adjusted_price"] <= upper_bound)
    ]


# ---------------------------------------------------------
# WEIGHTING
# ---------------------------------------------------------


def get_listing_weight(
    item: dict,
    provider_counts: Counter,
) -> float:
    score = max(
        item["score"],
        1,
    )

    provider = item["listing"].provider

    provider_count = max(
        provider_counts[provider],
        1,
    )

    similarity_weight = (score / 100) ** 2

    provider_balance = 1 / math.sqrt(provider_count)

    dom_weight = days_on_market_weight(item["listing"].days_on_market)

    return similarity_weight * provider_balance * dom_weight


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

        weighted_total += item["adjusted_price"] * weight

        total_weight += weight

    if total_weight == 0:
        return mean(item["adjusted_price"] for item in scored)

    return weighted_total / total_weight


def weighted_median_price(
    scored: list[dict],
) -> float:
    provider_counts = Counter(item["listing"].provider for item in scored)

    weighted: list[
        tuple[
            float,
            float,
        ]
    ] = []

    for item in scored:
        weight = get_listing_weight(
            item,
            provider_counts,
        )

        weighted.append(
            (
                item["adjusted_price"],
                weight,
            )
        )

    weighted.sort(key=lambda item: item[0])

    total_weight = sum(
        weight
        for (
            _,
            weight,
        ) in weighted
    )

    halfway = total_weight / 2

    running = 0.0

    for (
        price,
        weight,
    ) in weighted:
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
# FAIR PURCHASE PRICE
# ---------------------------------------------------------


def calculate_fair_purchase_price(
    adjusted_prices: list[float],
    weighted_median: float,
    subject_days_on_market: (int | None),
) -> dict:
    lower_quartile = percentile_price(
        adjusted_prices,
        0.25,
    )

    market_median = median(adjusted_prices)

    purchase_target = weighted_median

    dom_position_factor = 0.0

    if subject_days_on_market is not None and subject_days_on_market >= 0:
        dom_position_factor = min(
            (subject_days_on_market / 120),
            1.0,
        )

        purchase_target = (
            weighted_median - (weighted_median - lower_quartile) * dom_position_factor
        )

    low = min(
        lower_quartile,
        purchase_target,
    )

    high = max(
        purchase_target,
        market_median,
    )

    return {
        "value": round(
            purchase_target,
            2,
        ),
        "range": {
            "low": round(
                low,
                2,
            ),
            "high": round(
                high,
                2,
            ),
        },
        "lower_quartile_market": (
            round(
                lower_quartile,
                2,
            )
        ),
        "market_median": round(
            market_median,
            2,
        ),
        "days_on_market": (subject_days_on_market),
        "dom_position_factor": (
            round(
                dom_position_factor,
                3,
            )
        ),
        "method": ("normalized_comparable_market"),
    }


# ---------------------------------------------------------
# CONFIDENCE
# ---------------------------------------------------------


def determine_confidence(
    selected: list[dict],
    strategy: str,
    mileage_rate_samples: int,
    year_rate_samples: int,
) -> str:
    if not selected:
        return "low"

    strong_count = sum(1 for item in selected if (item["score"] >= 70))

    if (
        len(selected) >= 8
        and strong_count >= 5
        and mileage_rate_samples >= 6
        and year_rate_samples >= 6
    ):
        return "high"

    if (
        len(selected) >= 5
        and max(item["score"] for item in selected) >= 60
        and strategy != ("no_relevant_comparables")
    ):
        return "medium"

    return "low"


# ---------------------------------------------------------
# MAIN ANALYSIS
# ---------------------------------------------------------


def analyze_market(
    listings: list[ComparableListing],
    target_mileage: int,
    subject_year: int,
    subject_trim: str | None = None,
    subject_vin: str | None = None,
    subject_state: str | None = None,
    asking_price: float | None = None,
    subject_days_on_market: (int | None) = None,
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
            warning=("All returned listings failed market data validation.")
        )

    (
        mileage_rate,
        mileage_rate_samples,
        year_rate,
        year_rate_samples,
    ) = estimate_market_adjustment_rates(
        listings=(validated_listings),
        subject_trim=(subject_trim),
        subject_year=(subject_year),
        target_mileage=(target_mileage),
        subject_state=(subject_state),
    )

    (
        trim_levels,
        model_market_level,
    ) = estimate_trim_market_levels(
        listings=(validated_listings),
        subject_year=(subject_year),
        target_mileage=(target_mileage),
        mileage_rate=(mileage_rate),
        year_rate=(year_rate),
    )

    scored = build_normalized_comparables(
        listings=(validated_listings),
        subject_year=(subject_year),
        subject_trim=(subject_trim),
        target_mileage=(target_mileage),
        subject_state=(subject_state),
        subject_vin=(subject_vin),
        mileage_rate=(mileage_rate),
        year_rate=(year_rate),
        trim_levels=(trim_levels),
    )

    if not scored:
        return empty_analysis(
            warning=(
                "No comparable listings remained after excluding the subject vehicle."
            )
        )

    (
        selected,
        strategy,
    ) = select_best_comparables(scored)

    if not selected:
        return empty_analysis(
            warning=(
                "Listings were found, but none were sufficiently similar for valuation."
            )
        )

    before_outlier_removal = len(selected)

    selected = remove_price_outliers(selected)

    if not selected:
        return empty_analysis()

    weighted_average = weighted_average_price(selected)

    weighted_median = weighted_median_price(selected)

    comparable_market_value = weighted_median * 0.70 + weighted_average * 0.30

    adjusted_prices = [item["adjusted_price"] for item in selected]

    typical_low = percentile_price(
        adjusted_prices,
        0.25,
    )

    typical_high = percentile_price(
        adjusted_prices,
        0.75,
    )

    fair_purchase = calculate_fair_purchase_price(
        adjusted_prices=(adjusted_prices),
        weighted_median=(weighted_median),
        subject_days_on_market=(subject_days_on_market),
    )

    confidence = determine_confidence(
        selected=selected,
        strategy=strategy,
        mileage_rate_samples=(mileage_rate_samples),
        year_rate_samples=(year_rate_samples),
    )

    subject_trim_normalized = normalize_trim(subject_trim)

    subject_trim_data = trim_levels.get(subject_trim_normalized)

    subject_trim_premium = None

    if subject_trim_data and model_market_level is not None:
        subject_trim_premium = subject_trim_data["value"] - model_market_level

    provider_groups: dict[
        str,
        list[float],
    ] = defaultdict(list)

    for item in selected:
        provider = item["listing"].provider

        provider_groups[provider].append(item["adjusted_price"])

    provider_estimates = {
        provider: round(
            median(values),
            2,
        )
        for (
            provider,
            values,
        ) in provider_groups.items()
    }

    asking_price_analysis = None

    if asking_price is not None and asking_price > 0:
        asking_price_analysis = {
            "asking_price": (
                round(
                    asking_price,
                    2,
                )
            ),
            ("difference_from_fair_market"): round(
                asking_price - comparable_market_value,
                2,
            ),
            ("difference_from_fair_purchase"): round(
                asking_price - fair_purchase["value"],
                2,
            ),
        }

    top_comparables: list[dict] = []

    for item in selected[:10]:
        listing = item["listing"]

        top_comparables.append(
            {
                "score": (item["score"]),
                "provider": (listing.provider),
                "vin": (listing.vin),
                "year": (listing.year),
                "make": (listing.make),
                "model": (listing.model),
                "trim": (listing.trim),
                "raw_price": round(
                    item["raw_price"],
                    2,
                ),
                "adjusted_price": (
                    round(
                        item["adjusted_price"],
                        2,
                    )
                ),
                "mileage": (listing.mileage),
                "days_on_market": (listing.days_on_market),
                "city": (listing.city),
                "state": (listing.state),
                "listing_url": (listing.listing_url),
                "adjustments": {
                    key: round(
                        value,
                        2,
                    )
                    for (
                        key,
                        value,
                    ) in item["adjustments"].items()
                },
                "match_reasons": (item["reasons"]),
            }
        )

    warning = None

    if confidence == "low":
        warning = (
            "The available market "
            "data does not include "
            "enough high-quality "
            "comparable vehicles for "
            "a strong valuation."
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
        "providers_used": (len(provider_groups)),
        "provider_estimates": (provider_estimates),
        "comparable_market_value": (
            round(
                comparable_market_value,
                2,
            )
        ),
        # Compatibility with
        # existing API/frontend.
        "estimated_market_value": (
            round(
                comparable_market_value,
                2,
            )
        ),
        "weighted_average_price": (
            round(
                weighted_average,
                2,
            )
        ),
        "weighted_median_price": (
            round(
                weighted_median,
                2,
            )
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
        # Fair purchase value stays
        # independent of trade value.
        "fair_purchase_value": (fair_purchase["value"]),
        "fair_purchase_range": (fair_purchase["range"]),
        "fair_purchase_analysis": (fair_purchase),
        "asking_price_analysis": (asking_price_analysis),
        "market_normalization": {
            ("mileage_value_per_1000"): round(
                mileage_rate,
                2,
            ),
            ("mileage_rate_sample_count"): (mileage_rate_samples),
            ("year_value_per_year"): round(
                year_rate,
                2,
            ),
            ("year_rate_sample_count"): (year_rate_samples),
            "model_market_level": (
                round(
                    model_market_level,
                    2,
                )
                if (model_market_level is not None)
                else None
            ),
            "subject_trim": (subject_trim_normalized or None),
            ("subject_trim_market_level"): (
                subject_trim_data["value"] if subject_trim_data else None
            ),
            ("subject_trim_sample_count"): (
                subject_trim_data["sample_count"] if subject_trim_data else 0
            ),
            ("subject_trim_premium_vs_model"): (
                round(
                    subject_trim_premium,
                    2,
                )
                if (subject_trim_premium is not None)
                else None
            ),
            "trim_market_levels": (trim_levels),
        },
        "target_mileage": (target_mileage),
        "subject_days_on_market": (subject_days_on_market),
        "confidence": (confidence),
        "warning": (warning),
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
        "comparable_market_value": None,
        "estimated_market_value": None,
        "fair_purchase_value": None,
        "fair_purchase_range": None,
        "fair_purchase_analysis": None,
        "asking_price_analysis": None,
        "provider_estimates": {},
        "market_normalization": {},
        "confidence": "low",
        "warning": (warning or ("No usable comparable vehicles were found.")),
        "top_comparables": [],
    }
