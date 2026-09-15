from statistics import median


BASE_WEIGHTS = {
    "dealer_market_comparables": 1.60,
    "marketcheck": 1.00,
    "carsxe_retail": 1.00,
    # Ready for future integrations.
    "kbb_retail": 1.10,
    "vinaudit_retail": 1.00,
}


INTERNAL_CONFIDENCE_MULTIPLIER = {
    "high": 1.25,
    "medium": 1.00,
    "low": 0.65,
}


def valid_value(
    value: float | None,
) -> bool:
    return value is not None and value > 0


def build_source(
    source: str,
    value: float,
    weight: float,
) -> dict:
    return {
        "source": source,
        "value": float(value),
        "base_weight": weight,
        "effective_weight": weight,
        "outlier_adjusted": False,
    }


def apply_outlier_adjustment(
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

        # We do not delete a conflicting
        # valuation source. We reduce its
        # influence if it is far outside
        # the rest of the market evidence.
        if difference_percent > 0.15:
            source_copy["effective_weight"] *= 0.50

            source_copy["outlier_adjusted"] = True

        adjusted_sources.append(source_copy)

    return adjusted_sources


def calculate_weighted_value(
    sources: list[dict],
) -> float | None:
    if not sources:
        return None

    weighted_total = 0.0
    total_weight = 0.0

    for source in sources:
        weight = source["effective_weight"]

        weighted_total += source["value"] * weight

        total_weight += weight

    if total_weight <= 0:
        return None

    return weighted_total / total_weight


def determine_agreement(
    spread_percent: float,
) -> str:
    if spread_percent <= 5:
        return "strong"

    if spread_percent <= 10:
        return "reasonable"

    if spread_percent <= 18:
        return "mixed"

    return "weak"


def determine_confidence(
    source_count: int,
    internal_confidence: str,
    spread_percent: float,
) -> str:
    if source_count >= 3 and internal_confidence == "high" and spread_percent <= 10:
        return "high"

    if (
        source_count >= 2
        and internal_confidence in {"high", "medium"}
        and spread_percent <= 18
    ):
        return "medium"

    return "low"


def build_valuation_consensus(
    internal_value: float | None,
    internal_confidence: str,
    marketcheck_value: float | None,
    carsxe_retail_value: (float | None) = None,
    kbb_retail_value: (float | None) = None,
    vinaudit_retail_value: (float | None) = None,
) -> dict:
    sources: list[dict] = []

    if valid_value(internal_value):
        internal_multiplier = INTERNAL_CONFIDENCE_MULTIPLIER.get(
            internal_confidence,
            0.65,
        )

        internal_weight = (
            BASE_WEIGHTS["dealer_market_comparables"] * internal_multiplier
        )

        sources.append(
            build_source(
                source=("dealer_market_comparables"),
                value=internal_value,
                weight=internal_weight,
            )
        )

    if valid_value(marketcheck_value):
        sources.append(
            build_source(
                source="marketcheck",
                value=marketcheck_value,
                weight=BASE_WEIGHTS["marketcheck"],
            )
        )

    if valid_value(carsxe_retail_value):
        sources.append(
            build_source(
                source="carsxe_retail",
                value=carsxe_retail_value,
                weight=BASE_WEIGHTS["carsxe_retail"],
            )
        )

    if valid_value(kbb_retail_value):
        sources.append(
            build_source(
                source="kbb_retail",
                value=kbb_retail_value,
                weight=BASE_WEIGHTS["kbb_retail"],
            )
        )

    if valid_value(vinaudit_retail_value):
        sources.append(
            build_source(
                source="vinaudit_retail",
                value=vinaudit_retail_value,
                weight=BASE_WEIGHTS["vinaudit_retail"],
            )
        )

    if not sources:
        return {
            "fair_market_value": None,
            "fair_sale_value": None,
            "consensus_value": None,
            "source_count": 0,
            "sources": [],
            "confidence": "low",
            "agreement": "unavailable",
            "method": ("multi_source_weighted_retail"),
            "warning": ("No usable retail valuation sources were available."),
        }

    sources = apply_outlier_adjustment(sources)

    consensus_value = calculate_weighted_value(sources)

    if consensus_value is None:
        return {
            "fair_market_value": None,
            "fair_sale_value": None,
            "consensus_value": None,
            "source_count": len(sources),
            "sources": sources,
            "confidence": "low",
            "agreement": "unavailable",
            "method": ("multi_source_weighted_retail"),
            "warning": ("Retail market value could not be calculated."),
        }

    source_values = [source["value"] for source in sources]

    minimum_value = min(source_values)

    maximum_value = max(source_values)

    spread = maximum_value - minimum_value

    spread_percent = spread / consensus_value * 100 if consensus_value > 0 else 0.0

    agreement = determine_agreement(spread_percent)

    confidence = determine_confidence(
        source_count=len(sources),
        internal_confidence=(internal_confidence),
        spread_percent=(spread_percent),
    )

    source_results = []

    for source in sources:
        difference = source["value"] - consensus_value

        difference_percent = (
            difference / consensus_value * 100 if consensus_value > 0 else 0.0
        )

        source_results.append(
            {
                "source": (source["source"]),
                "value": round(
                    source["value"],
                    2,
                ),
                "base_weight": round(
                    source["base_weight"],
                    2,
                ),
                "effective_weight": (
                    round(
                        source["effective_weight"],
                        2,
                    )
                ),
                "difference_from_consensus": (
                    round(
                        difference,
                        2,
                    )
                ),
                "difference_percent": (
                    round(
                        difference_percent,
                        2,
                    )
                ),
                "outlier_adjusted": (source["outlier_adjusted"]),
            }
        )

    warning = None

    if agreement == "weak":
        warning = (
            "Retail valuation sources "
            "show substantial disagreement. "
            "Review the comparable vehicles "
            "and vehicle details before "
            "relying on this estimate."
        )

    return {
        "fair_market_value": round(
            consensus_value,
            2,
        ),
        # Kept for compatibility with
        # existing frontend/backend naming.
        "fair_sale_value": round(
            consensus_value,
            2,
        ),
        "consensus_value": round(
            consensus_value,
            2,
        ),
        "comparable_market_value": (
            round(
                internal_value,
                2,
            )
            if valid_value(internal_value)
            else None
        ),
        "source_count": len(sources),
        "source_range": {
            "low": round(
                minimum_value,
                2,
            ),
            "high": round(
                maximum_value,
                2,
            ),
        },
        "source_spread": round(
            spread,
            2,
        ),
        "source_spread_percent": (
            round(
                spread_percent,
                2,
            )
        ),
        "sources": (source_results),
        "internal_confidence": (internal_confidence),
        "agreement": agreement,
        "confidence": confidence,
        "method": ("multi_source_weighted_retail"),
        "warning": warning,
    }
