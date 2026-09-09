from pydantic import BaseModel


class VehicleSearch(BaseModel):
    year: int
    make: str
    model: str
    trim: str | None = None
    mileage: int
    zip_code: str


class ComparableListing(BaseModel):
    provider: str
    source_site: str | None = None

    vin: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None

    price: float
    mileage: int | None = None

    dealer: str | None = None
    city: str | None = None
    state: str | None = None

    days_on_market: int | None = None
    data_quality: float | None = None

    listing_url: str | None = None
