from statistics import mean


def build_valuation_consensus(
    internal_value: float | None,
    internal_confidence: str,
    marketcheck_value: float | None,
    carsxe_retail_value: float | None = None,
) -> dict:
    external_benchmarks = []

    if marketcheck_value is not None and marketcheck_value > 0:
        external_benchmarks.append(
            {
                "source": "marketcheck",
                "value": float(marketcheck_value),
            }
        )

    if carsxe_retail_value is not None and carsxe_retail_value > 0:
        external_benchmarks.append(
            {
                "source": "carsxe_clean_retail",
                "value": float(carsxe_retail_value),
            }
        )

    # Dealer-market comparables are now the
    # primary source of fair sale value.
    if internal_value is None or internal_value <= 0:
        return {
            "fair_sale_value": None,
            "consensus_value": None,
            "primary_source": ("dealer_market_comparables"),
            "internal_confidence": (internal_confidence),
            "confidence": "low",
            "external_benchmarks": (external_benchmarks),
            "external_average": None,
            "external_average_difference": (None),
            "external_average_difference_percent": (None),
            "validation_status": ("no_primary_market_value"),
            "method": ("market_comparables_primary_external_validation"),
        }

    fair_sale_value = float(internal_value)

    benchmark_results = []

    for benchmark in external_benchmarks:
        benchmark_value = benchmark["value"]

        difference = benchmark_value - fair_sale_value

        difference_percent = difference / fair_sale_value * 100

        benchmark_results.append(
            {
                "source": (benchmark["source"]),
                "value": round(
                    benchmark_value,
                    2,
                ),
                "difference": round(
                    difference,
                    2,
                ),
                "difference_percent": (
                    round(
                        difference_percent,
                        2,
                    )
                ),
            }
        )

    external_average = None
    external_difference = None
    external_difference_percent = None

    if external_benchmarks:
        external_average = mean(benchmark["value"] for benchmark in external_benchmarks)

        external_difference = external_average - fair_sale_value

        external_difference_percent = external_difference / fair_sale_value * 100

        absolute_difference_percent = abs(external_difference_percent)

        if absolute_difference_percent <= 5:
            validation_status = "aligned"

        elif absolute_difference_percent <= 10:
            validation_status = "reasonable_variance"

        else:
            validation_status = "divergent"

    else:
        validation_status = "external_validation_unavailable"

    # External providers validate the market
    # estimate but do not change its value.
    if internal_confidence == "high":
        if validation_status == "aligned":
            final_confidence = "high"

        elif validation_status == "reasonable_variance":
            final_confidence = "medium"

        elif validation_status == "external_validation_unavailable":
            final_confidence = "high"

        else:
            final_confidence = "low"

    elif internal_confidence == "medium":
        if validation_status in {
            "aligned",
            "reasonable_variance",
        }:
            final_confidence = "medium"

        elif validation_status == "external_validation_unavailable":
            final_confidence = "medium"

        else:
            final_confidence = "low"

    else:
        final_confidence = "low"

    return {
        "fair_sale_value": round(
            fair_sale_value,
            2,
        ),
        # Kept for compatibility with
        # main.py and dealer economics.
        "consensus_value": round(
            fair_sale_value,
            2,
        ),
        "primary_source": ("dealer_market_comparables"),
        "internal_confidence": (internal_confidence),
        "confidence": (final_confidence),
        "external_benchmarks": (benchmark_results),
        "external_average": (
            round(
                external_average,
                2,
            )
            if external_average is not None
            else None
        ),
        "external_average_difference": (
            round(
                external_difference,
                2,
            )
            if external_difference is not None
            else None
        ),
        "external_average_difference_percent": (
            round(
                external_difference_percent,
                2,
            )
            if external_difference_percent is not None
            else None
        ),
        "validation_status": (validation_status),
        "method": ("market_comparables_primary_external_validation"),
    }
