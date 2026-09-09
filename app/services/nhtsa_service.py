import httpx
from fastapi import HTTPException


NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues"


async def decode_vin(vin: str) -> dict:
    vin = vin.strip().upper()

    if len(vin) != 17:
        raise HTTPException(
            status_code=400,
            detail="VIN must be 17 characters.",
        )

    url = f"{NHTSA_URL}/{vin}"

    params = {
        "format": "json",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            url,
            params=params,
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail="NHTSA VIN lookup failed.",
        )

    data = response.json()

    results = data.get("Results", [])

    if not results:
        raise HTTPException(
            status_code=404,
            detail="VIN could not be decoded.",
        )

    vehicle = results[0]

    year = vehicle.get("ModelYear")
    make = vehicle.get("Make")
    model = vehicle.get("Model")
    trim = vehicle.get("Trim")

    if not year or not make or not model:
        raise HTTPException(
            status_code=404,
            detail="VIN decoded, but required vehicle information was missing.",
        )

    return {
        "vin": vin,
        "year": int(year),
        "make": make,
        "model": model,
        "trim": trim or None,
        "body_class": vehicle.get("BodyClass") or None,
        "drive_type": vehicle.get("DriveType") or None,
        "fuel_type": vehicle.get("FuelTypePrimary") or None,
        "engine_cylinders": vehicle.get("EngineCylinders") or None,
        "engine_displacement_l": vehicle.get("DisplacementL") or None,
        "manufacturer": vehicle.get("Manufacturer") or None,
    }
