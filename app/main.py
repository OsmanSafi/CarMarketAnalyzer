import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services.carsxe_service import (
    get_carsxe_market_value,
)
from app.services.dealer_economics_service import (
    AccidentHistory,
    MechanicalIssues,
    TitleStatus,
    VehicleCondition,
    estimate_dealer_economics,
    select_carsxe_wholesale,
)
from app.services.market_service import (
    get_market_listings,
)
from app.services.marketcheck_service import (
    get_marketcheck_price,
)
from app.services.nhtsa_service import decode_vin
from app.services.pricing_service import (
    analyze_market,
)
from app.services.valuation_consensus_service import (
    build_valuation_consensus,
)

app = FastAPI(
    title="Car Market Analyzer API",
    description=(
        "Open-source multi-source automotive pricing and dealer economics platform"
    ),
    version="0.10.0",
)

cors_origins = os.getenv(
    "CORS_ORIGINS",
    ("http://localhost:5173,http://127.0.0.1:5173"),
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "name": "Car Market Analyzer",
        "version": "0.10.0",
        "status": "running",
    }


@app.get("/vin/{vin}")
async def vin_lookup(
    vin: str,
):
    return await decode_vin(vin)


@app.get("/car")
async def get_car(
    year: int,
    make: str,
    model: str,
    mileage: int,
    zip_code: str,
    trim: str | None = None,
):
    market_data = await get_market_listings(
        year=year,
        make=make,
        model=model,
        trim=trim,
        mileage=mileage,
        zip_code=zip_code,
    )

    analysis = analyze_market(
        listings=market_data["listings"],
        target_mileage=mileage,
        subject_year=year,
        subject_trim=trim,
    )

    return {
        "vehicle": {
            "year": year,
            "make": make,
            "model": model,
            "trim": trim,
            "mileage": mileage,
            "zip_code": zip_code,
        },
        "market_analysis": analysis,
        "market_data": {
            "provider_counts": market_data["provider_counts"],
            "provider_status": market_data["provider_status"],
            "before_deduplication": (market_data["before_deduplication"]),
            "after_deduplication": (market_data["after_deduplication"]),
        },
        "listings": market_data["listings"],
    }


def compare_values(
    internal_value: float | None,
    external_value: float | None,
) -> dict | None:
    if internal_value is None or external_value is None or external_value <= 0:
        return None

    difference = external_value - internal_value

    difference_percent = difference / external_value * 100

    return {
        "difference": round(
            difference,
            2,
        ),
        "difference_percent": round(
            difference_percent,
            2,
        ),
    }


@app.get("/valuation")
async def get_valuation(
    vin: str,
    mileage: int,
    zip_code: str,
    state: str | None = None,
    condition: VehicleCondition = "unknown",
    accident_history: AccidentHistory = "unknown",
    title_status: TitleStatus = "unknown",
    mechanical_issues: MechanicalIssues = "unknown",
    asking_price: float | None = None,
):
    vehicle = await decode_vin(vin)

    (
        market_data,
        marketcheck_data,
        carsxe_data,
    ) = await asyncio.gather(
        get_market_listings(
            year=vehicle["year"],
            make=vehicle["make"],
            model=vehicle["model"],
            trim=vehicle["trim"],
            mileage=mileage,
            zip_code=zip_code,
        ),
        get_marketcheck_price(
            vin=vin,
            mileage=mileage,
            zip_code=zip_code,
        ),
        get_carsxe_market_value(
            vin=vin,
            mileage=mileage,
            state=state,
        ),
    )

    analysis = analyze_market(
        listings=market_data["listings"],
        target_mileage=mileage,
        subject_year=vehicle["year"],
        subject_trim=vehicle["trim"],
        subject_vin=vehicle["vin"],
    )

    internal_value = analysis.get("estimated_market_value")

    marketcheck_value = marketcheck_data.get("marketcheck_price")

    carsxe_retail_value = carsxe_data.get(
        "retail",
        {},
    ).get("clean")

    valuation_consensus = build_valuation_consensus(
        internal_value=internal_value,
        internal_confidence=analysis["confidence"],
        marketcheck_value=(marketcheck_value),
        carsxe_retail_value=(carsxe_retail_value),
    )

    wholesale_tier, wholesale_value = select_carsxe_wholesale(
        wholesale_values=(
            carsxe_data.get(
                "wholesale",
                {},
            )
        ),
        condition=condition,
    )

    external_valuations = {
        "marketcheck": {
            "status": marketcheck_data.get("status"),
            "retail_value": (marketcheck_value),
            "msrp": marketcheck_data.get("msrp"),
            "comparison_to_internal": (
                compare_values(
                    internal_value,
                    marketcheck_value,
                )
            ),
        },
        "carsxe": {
            "status": carsxe_data.get("status"),
            "publish_date": (carsxe_data.get("publish_date")),
            "state": carsxe_data.get("state"),
            "retail": carsxe_data.get(
                "retail",
                {},
            ),
            "wholesale": (
                carsxe_data.get(
                    "wholesale",
                    {},
                )
            ),
            "selected_wholesale_tier": (wholesale_tier),
            "selected_wholesale_value": (wholesale_value),
            "comparison_to_internal": (
                compare_values(
                    internal_value,
                    carsxe_retail_value,
                )
            ),
        },
    }

    consensus_value = valuation_consensus.get("consensus_value")

    dealer_economics = None

    if consensus_value is not None:
        dealer_economics = estimate_dealer_economics(
            retail_market_value=(consensus_value),
            mileage=mileage,
            subject_year=(vehicle["year"]),
            confidence=(valuation_consensus["confidence"]),
            condition=condition,
            accident_history=(accident_history),
            title_status=(title_status),
            mechanical_issues=(mechanical_issues),
            asking_price=(asking_price),
            carsxe_wholesale_value=(wholesale_value),
            carsxe_wholesale_tier=(wholesale_tier),
        )

    return {
        "vehicle": {
            **vehicle,
            "mileage": mileage,
            "zip_code": zip_code,
            "state": state,
        },
        "market_analysis": analysis,
        "external_valuations": (external_valuations),
        "valuation_consensus": (valuation_consensus),
        "dealer_economics": (dealer_economics),
        "market_data": {
            "provider_counts": (market_data["provider_counts"]),
            "provider_status": (market_data["provider_status"]),
            "before_deduplication": (market_data["before_deduplication"]),
            "after_deduplication": (market_data["after_deduplication"]),
        },
        "listings": market_data["listings"],
    }
