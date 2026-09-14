from datetime import datetime, timezone
from statistics import mean, median
from typing import Literal

VehicleCondition = Literal[
    "unknown",
    "excellent",
    "very_good",
    "good",
    "fair",
    "poor",
]

AccidentHistory = Literal[
    "unknown",
    "none",
    "minor",
    "major",
]

TitleStatus = Literal[
    "unknown",
    "clean",
    "rebuilt",
    "salvage",
]

MechanicalIssues = Literal[
    "unknown",
    "none",
    "minor",
    "major",
]


PUBLIC_DEALER_GPU = {
    "AutoNation Q2 2026": 1582.0,
    "CarMax Q1 FY2027": 2177.0,
    "Carvana FY2025": 3315.0,
}

GPU_MEDIAN = median(PUBLIC_DEALER_GPU.values())


CONDITION_RECON = {
    "unknown": 150.0,
    "excellent": -150.0,
    "very_good": 0.0,
    "good": 250.0,
    "fair": 900.0,
    "poor": 2000.0,
}

ACCIDENT_RECON = {
    "unknown": 100.0,
    "none": 0.0,
    "minor": 500.0,
    "major": 1500.0,
}

TITLE_RECON = {
    "unknown": 0.0,
    "clean": 0.0,
    "rebuilt": 300.0,
    "salvage": 600.0,
}

MECHANICAL_RECON = {
    "unknown": 200.0,
    "none": 0.0,
    "minor": 750.0,
    "major": 2500.0,
}


ACCIDENT_RETAIL = {
    "unknown": 1.00,
    "none": 1.00,
    "minor": 0.97,
    "major": 0.88,
}

TITLE_RETAIL = {
    "unknown": 1.00,
    "clean": 1.00,
    "rebuilt": 0.78,
    "salvage": 0.60,
}


CARSXE_CONDITION_MAP = {
    "unknown": "average",
    "excellent": "excellent",
    "very_good": "clean",
    "good": "clean",
    "fair": "average",
    "poor": "rough",
}


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


def select_carsxe_wholesale(
    wholesale_values: dict,
    condition: VehicleCondition,
) -> tuple[str, float | None]:
    tier = CARSXE_CONDITION_MAP.get(
        condition,
        "average",
    )

    value = wholesale_values.get(tier)

    if isinstance(value, (int, float)):
        return tier, float(value)

    return tier, None


def base_reconditioning(
    mileage: int,
) -> float:
    if mileage < 30000:
        return 450.0

    if mileage < 60000:
        return 650.0

    if mileage < 90000:
        return 850.0

    if mileage < 120000:
        return 1100.0

    if mileage < 160000:
        return 1450.0

    return 1900.0


def estimate_dealer_economics(
    retail_market_value: float,
    mileage: int,
    subject_year: int,
    confidence: str,
    condition: VehicleCondition = "unknown",
    accident_history: AccidentHistory = "unknown",
    title_status: TitleStatus = "unknown",
    mechanical_issues: MechanicalIssues = "unknown",
    asking_price: float | None = None,
    carsxe_wholesale_value: float | None = None,
    carsxe_wholesale_tier: str | None = None,
) -> dict:
    current_year = datetime.now(timezone.utc).year

    vehicle_age = max(
        0,
        current_year - subject_year,
    )

    recon_breakdown = {
        "base_from_mileage": (base_reconditioning(mileage)),
        "age_adjustment": min(
            700.0,
            max(
                0,
                vehicle_age - 5,
            )
            * 100.0,
        ),
        "condition_adjustment": (CONDITION_RECON[condition]),
        "accident_adjustment": (ACCIDENT_RECON[accident_history]),
        "title_adjustment": (TITLE_RECON[title_status]),
        "mechanical_adjustment": (MECHANICAL_RECON[mechanical_issues]),
    }

    reconditioning = max(
        350.0,
        sum(recon_breakdown.values()),
    )

    permanent_retail_factor = (
        ACCIDENT_RETAIL[accident_history] * TITLE_RETAIL[title_status]
    )

    expected_retail = max(
        0.0,
        retail_market_value * permanent_retail_factor,
    )

    percentage_gpu = expected_retail * 0.075

    target_gross_profit = clamp(
        percentage_gpu * 0.60 + GPU_MEDIAN * 0.40,
        1500.0,
        3500.0,
    )

    other_direct_costs = clamp(
        expected_retail * 0.0125,
        250.0,
        800.0,
    )

    modeled_acquisition = max(
        0.0,
        expected_retail - target_gross_profit - reconditioning - other_direct_costs,
    )

    acquisition_sources = [
        {
            "source": ("dealer_economics_model"),
            "value": modeled_acquisition,
        }
    ]

    if carsxe_wholesale_value is not None and carsxe_wholesale_value > 0:
        acquisition_sources.append(
            {
                "source": ("carsxe_wholesale"),
                "value": float(carsxe_wholesale_value),
            }
        )

    acquisition_midpoint = mean(source["value"] for source in acquisition_sources)

    acquisition_values = [source["value"] for source in acquisition_sources]

    acquisition_spread = (
        max(acquisition_values) - min(acquisition_values)
        if len(acquisition_values) > 1
        else 0.0
    )

    acquisition_spread_percent = (
        acquisition_spread / acquisition_midpoint * 100
        if acquisition_midpoint > 0
        else 0.0
    )

    appraisal_inputs = {
        "condition": condition,
        "accident_history": (accident_history),
        "title_status": title_status,
        "mechanical_issues": (mechanical_issues),
    }

    unknown_inputs = sum(value == "unknown" for value in appraisal_inputs.values())

    base_uncertainty = {
        "high": 0.04,
        "medium": 0.06,
        "low": 0.09,
    }.get(
        confidence,
        0.09,
    )

    if len(acquisition_sources) >= 2:
        base_uncertainty = max(
            0.035,
            base_uncertainty - 0.015,
        )

    uncertainty_percent = min(
        0.16,
        base_uncertainty + unknown_inputs * 0.0125,
    )

    uncertainty_amount = max(
        750.0,
        acquisition_midpoint * uncertainty_percent,
    )

    acquisition_low = max(
        0.0,
        acquisition_midpoint - uncertainty_amount,
    )

    acquisition_high = acquisition_midpoint + uncertainty_amount

    dealer_cost_basis = acquisition_midpoint + reconditioning + other_direct_costs

    projected_gross_spread = expected_retail - dealer_cost_basis

    projected_margin = (
        projected_gross_spread / expected_retail * 100 if expected_retail > 0 else 0.0
    )

    asking_analysis = None

    if asking_price is not None and asking_price > 0:
        asking_spread = asking_price - dealer_cost_basis

        asking_analysis = {
            "asking_price": round(
                asking_price,
                2,
            ),
            "asking_vs_estimated_retail": (
                round(
                    asking_price - expected_retail,
                    2,
                )
            ),
            "estimated_gross_spread": (
                round(
                    asking_spread,
                    2,
                )
            ),
            "estimated_gross_margin_percent": (
                round(
                    asking_spread / asking_price * 100,
                    2,
                )
            ),
        }

    if confidence == "low" or unknown_inputs >= 3:
        economics_confidence = "low"

    elif (
        len(acquisition_sources) >= 2
        and acquisition_spread_percent <= 8
        and unknown_inputs == 0
    ):
        economics_confidence = "high"

    else:
        economics_confidence = "medium"

    return {
        "retail_market_anchor": round(
            retail_market_value,
            2,
        ),
        "expected_retail_sale_price": (
            round(
                expected_retail,
                2,
            )
        ),
        "modeled_dealer_acquisition": (
            round(
                modeled_acquisition,
                2,
            )
        ),
        "carsxe_wholesale_benchmark": {
            "tier": (carsxe_wholesale_tier),
            "value": (
                round(
                    carsxe_wholesale_value,
                    2,
                )
                if carsxe_wholesale_value is not None
                else None
            ),
        },
        "estimated_dealer_acquisition": {
            "low": round(
                acquisition_low,
                2,
            ),
            "high": round(
                acquisition_high,
                2,
            ),
            "midpoint": round(
                acquisition_midpoint,
                2,
            ),
            "sources": [
                {
                    "source": source["source"],
                    "value": round(
                        source["value"],
                        2,
                    ),
                }
                for source in acquisition_sources
            ],
            "source_spread": round(
                acquisition_spread,
                2,
            ),
            "source_spread_percent": (
                round(
                    acquisition_spread_percent,
                    2,
                )
            ),
        },
        "estimated_reconditioning": {
            "total": round(
                reconditioning,
                2,
            ),
            "breakdown": {
                key: round(value, 2) for key, value in recon_breakdown.items()
            },
        },
        "estimated_other_direct_costs": (
            round(
                other_direct_costs,
                2,
            )
        ),
        "estimated_dealer_cost_basis": (
            round(
                dealer_cost_basis,
                2,
            )
        ),
        "projected_vehicle_gross_spread": (
            round(
                projected_gross_spread,
                2,
            )
        ),
        "projected_vehicle_gross_margin_percent": (
            round(
                projected_margin,
                2,
            )
        ),
        "asking_price_analysis": (asking_analysis),
        "retail_adjustments": {
            "accident_history": (ACCIDENT_RETAIL[accident_history]),
            "title_status": (TITLE_RETAIL[title_status]),
            "combined": round(
                permanent_retail_factor,
                4,
            ),
        },
        "appraisal_inputs": (appraisal_inputs),
        "unknown_appraisal_inputs": (unknown_inputs),
        "confidence": (economics_confidence),
        "uncertainty": {
            "percentage": round(
                uncertainty_percent * 100,
                2,
            ),
            "amount": round(
                uncertainty_amount,
                2,
            ),
        },
        "calibration": {
            "public_used_vehicle_gross_profit_per_unit": (PUBLIC_DEALER_GPU),
            "benchmark_median": round(
                GPU_MEDIAN,
                2,
            ),
            "benchmark_as_of": ("2026-09"),
        },
        "disclaimer": (
            "Dealer acquisition, "
            "reconditioning, cost basis, "
            "and gross spread are modeled "
            "estimates and third-party "
            "valuation benchmarks, not "
            "actual dealer records. Gross "
            "spread excludes SG&A, financing, "
            "commissions, taxes, and other "
            "dealership overhead."
        ),
    }
