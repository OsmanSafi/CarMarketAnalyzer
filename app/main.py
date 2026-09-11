import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services.market_service import get_market_listings
from app.services.nhtsa_service import decode_vin
from app.services.pricing_service import analyze_market

app = FastAPI(
    title="Car Market Analyzer API",
    description=("Open-source multi-source automotive pricing and valuation platform"),
    version="0.6.0",
)

cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
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
        "version": "0.6.0",
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
            "before_deduplication": market_data["before_deduplication"],
            "after_deduplication": market_data["after_deduplication"],
        },
        "listings": market_data["listings"],
    }


@app.get("/valuation")
async def get_valuation(
    vin: str,
    mileage: int,
    zip_code: str,
):
    vehicle = await decode_vin(vin)

    market_data = await get_market_listings(
        year=vehicle["year"],
        make=vehicle["make"],
        model=vehicle["model"],
        trim=vehicle["trim"],
        mileage=mileage,
        zip_code=zip_code,
    )

    analysis = analyze_market(
        listings=market_data["listings"],
        target_mileage=mileage,
        subject_year=vehicle["year"],
        subject_trim=vehicle["trim"],
        subject_vin=vehicle["vin"],
    )

    return {
        "vehicle": {
            **vehicle,
            "mileage": mileage,
            "zip_code": zip_code,
        },
        "market_analysis": analysis,
        "market_data": {
            "provider_counts": market_data["provider_counts"],
            "provider_status": market_data["provider_status"],
            "before_deduplication": market_data["before_deduplication"],
            "after_deduplication": market_data["after_deduplication"],
        },
        "listings": market_data["listings"],
    }
