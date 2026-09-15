from statistics import median


SOURCE_WEIGHTS = {
    # Actual current offers carry the most weight
    # because someone is willing to buy the car
    # for this amount right now.
    "carmax_offer": 1.50,
    "carvana_offer": 1.50,
    "dealer_offer": 1.40,
    # External wholesale / trade benchmarks.
    "carsxe_wholesale": 1.00,
    "kbb_trade": 1.00,
    "vinaudit_trade": 1.00,
    # Our own modeled dealer acquisition estimate
    # is useful but is not an actual offer.
    "dealer_acquisition_model": 0.75,
}


def valid_value(
    value: float | None,
) -> bool:
    return value is not None and value > 0


def source_type(
    source: str,
) -> str:
    if source in {
        "carmax_offer",
        "carvana_offer",
        "dealer_offer",
    }:
        return "cash_offer"

    if source == "dealer_acquisition_model":
        return "modeled_estimate"

    return "valuation_benchmark"


def build_source(
    source: str,
    value: float,
    user_entered: bool = False,
    verified: bool = False,
) -> dict:
    return {
        "source": source,
        "value": float(value),
        "weight": SOURCE_WEIGHTS.get(
            source,
            1.0,
        ),
        "type": source_type(source),
        "user_entered": user_entered,
        "verified": verified,
    }


def apply_outlier_adjustments(
    sources: list[dict],
) -> list[dict]:
    if len(sources) < 3:
        return sources

    values = [source["value"] for source in sources]

    center = median(values)

    if center <= 0:
        return sources

    adjusted_sources = []

    for source in sources:
        source_copy = source.copy()

        difference_percent = abs(source["value"] - center) / center

        outlier = False

        # A source more than 25% away from
        # the median is not discarded, but
        # its influence is reduced.
        if difference_percent > 0.25:
            source_copy["weight"] *= 0.50
            outlier = True

        source_copy["outlier_adjusted"] = outlier

        adjusted_sources.append(source_copy)

    return adjusted_sources


def weighted_average(
    sources: list[dict],
) -> float | None:
    if not sources:
        return None

    weighted_total = 0.0
    total_weight = 0.0

    for source in sources:
        weight = source["weight"]

        weighted_total += source["value"] * weight

        total_weight += weight

    if total_weight <= 0:
        return None

    return weighted_total / total_weight


def weighted_average_deviation(
    sources: list[dict],
    center: float,
) -> float:
    if not sources:
        return 0.0

    weighted_total = 0.0
    total_weight = 0.0

    for source in sources:
        weight = source["weight"]

        weighted_total += abs(source["value"] - center) * weight

        total_weight += weight

    if total_weight <= 0:
        return 0.0

    return weighted_total / total_weight


def determine_confidence(
    sources: list[dict],
    spread_percent: float,
) -> str:
    source_count = len(sources)

    actual_offer_count = sum(source["type"] == "cash_offer" for source in sources)

    if source_count >= 3 and actual_offer_count >= 1 and spread_percent <= 12:
        return "high"

    if source_count >= 2 and spread_percent <= 18:
        return "medium"

    return "low"


def build_trade_valuation(
    modeled_dealer_acquisition: (float | None),
    carsxe_wholesale_value: (float | None),
    carmax_offer: float | None = None,
    carvana_offer: float | None = None,
    dealer_offer: float | None = None,
    kbb_trade_value: float | None = None,
    vinaudit_trade_value: (float | None) = None,
    carmax_verified: bool = False,
    carvana_verified: bool = False,
    dealer_offer_verified: bool = False,
) -> dict:
    sources: list[dict] = []

    if valid_value(modeled_dealer_acquisition):
        sources.append(
            build_source(
                source=("dealer_acquisition_model"),
                value=(modeled_dealer_acquisition),
            )
        )

    if valid_value(carsxe_wholesale_value):
        sources.append(
            build_source(
                source="carsxe_wholesale",
                value=(carsxe_wholesale_value),
            )
        )

    if valid_value(carmax_offer):
        sources.append(
            build_source(
                source="carmax_offer",
                value=carmax_offer,
                user_entered=True,
                verified=carmax_verified,
            )
        )

    if valid_value(carvana_offer):
        sources.append(
            build_source(
                source="carvana_offer",
                value=carvana_offer,
                user_entered=True,
                verified=carvana_verified,
            )
        )

    if valid_value(dealer_offer):
        sources.append(
            build_source(
                source="dealer_offer",
                value=dealer_offer,
                user_entered=True,
                verified=(dealer_offer_verified),
            )
        )

    if valid_value(kbb_trade_value):
        sources.append(
            build_source(
                source="kbb_trade",
                value=kbb_trade_value,
            )
        )

    if valid_value(vinaudit_trade_value):
        sources.append(
            build_source(
                source="vinaudit_trade",
                value=(vinaudit_trade_value),
            )
        )

    if not sources:
        return {
            "estimated_trade_value": None,
            "trade_range": None,
            "source_count": 0,
            "sources": [],
            "confidence": "low",
            "method": ("multi_source_weighted_trade"),
            "warning": ("No usable trade-in valuation sources were available."),
        }

    sources = apply_outlier_adjustments(sources)

    estimated_trade_value = weighted_average(sources)

    if estimated_trade_value is None:
        return {
            "estimated_trade_value": None,
            "trade_range": None,
            "source_count": len(sources),
            "sources": sources,
            "confidence": "low",
            "method": ("multi_source_weighted_trade"),
            "warning": ("Trade value could not be calculated."),
        }

    values = [source["value"] for source in sources]

    minimum_source = min(values)
    maximum_source = max(values)

    source_spread = maximum_source - minimum_source

    source_spread_percent = (
        source_spread / estimated_trade_value * 100
        if estimated_trade_value > 0
        else 0.0
    )

    average_deviation = weighted_average_deviation(
        sources=sources,
        center=estimated_trade_value,
    )

    # Always provide some uncertainty,
    # even if the sources happen to agree
    # almost exactly.
    uncertainty = max(
        500.0,
        average_deviation,
    )

    trade_low = max(
        0.0,
        estimated_trade_value - uncertainty,
    )

    trade_high = estimated_trade_value + uncertainty

    confidence = determine_confidence(
        sources=sources,
        spread_percent=(source_spread_percent),
    )

    actual_offers = [source for source in sources if (source["type"] == "cash_offer")]

    best_actual_offer = None

    if actual_offers:
        best_source = max(
            actual_offers,
            key=lambda source: source["value"],
        )

        best_actual_offer = {
            "source": (best_source["source"]),
            "value": round(
                best_source["value"],
                2,
            ),
            "verified": (best_source["verified"]),
        }

    return {
        "estimated_trade_value": round(
            estimated_trade_value,
            2,
        ),
        "trade_range": {
            "low": round(
                trade_low,
                2,
            ),
            "high": round(
                trade_high,
                2,
            ),
        },
        "source_range": {
            "low": round(
                minimum_source,
                2,
            ),
            "high": round(
                maximum_source,
                2,
            ),
        },
        "source_spread": round(
            source_spread,
            2,
        ),
        "source_spread_percent": round(
            source_spread_percent,
            2,
        ),
        "source_count": len(sources),
        "actual_offer_count": len(actual_offers),
        "best_actual_offer": (best_actual_offer),
        "sources": [
            {
                "source": (source["source"]),
                "value": round(
                    source["value"],
                    2,
                ),
                "weight": round(
                    source["weight"],
                    2,
                ),
                "type": (source["type"]),
                "user_entered": (source["user_entered"]),
                "verified": (source["verified"]),
                "outlier_adjusted": (
                    source.get(
                        "outlier_adjusted",
                        False,
                    )
                ),
            }
            for source in sources
        ],
        "confidence": confidence,
        "method": ("multi_source_weighted_trade"),
        "weighting": {
            "cash_offer": ("highest_weight"),
            "wholesale_benchmark": ("standard_weight"),
            "modeled_estimate": ("lower_weight"),
        },
        "disclaimer": (
            "Trade-in value is an estimate "
            "derived from available wholesale "
            "benchmarks, modeled acquisition "
            "values, and user-provided offers. "
            "Actual offers may vary based on "
            "inspection, condition, location, "
            "market demand, and offer date."
        ),
    }
