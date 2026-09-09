# Car Market Analyzer

Car Market Analyzer is an open-source vehicle valuation application that combines VIN decoding, live marketplace listings, comparable-vehicle scoring, and pricing analysis to estimate a vehicle's retail and trade-in value.

The project is built as a portfolio-quality full-stack application with a FastAPI backend and a React + TypeScript frontend.

## Features

- Decode a vehicle from its VIN using NHTSA vPIC
- Search marketplace listings from multiple providers
- Filter suspicious or invalid listing data
- Exclude the subject vehicle from its own valuation
- Score comparable vehicles using:
  - trim similarity
  - model year
  - mileage
  - provider quality
- Estimate:
  - market value
  - fair purchase range
  - trade-in range
- Show confidence levels based on comparable-data quality
- Display top comparable vehicles and listing links
- Handle invalid VINs, invalid mileage, invalid ZIP codes, API failures, and sparse market data

## Current Status

**MVP / Beta**

The core valuation pipeline and frontend are working end-to-end.

Current development priorities include:

- stronger geographic/local-market weighting
- improved coverage for vehicles with limited comparable data
- additional marketplace data sources
- production deployment
- richer charts and market insights

## Tech Stack

### Backend

- Python 3.13
- FastAPI
- Uvicorn
- HTTPX
- Pydantic
- python-dotenv

### Frontend

- React
- TypeScript
- Vite
- ESLint
- CSS

### Data Sources

- NHTSA vPIC — VIN decoding
- Auto.dev — marketplace listings
- Vehicles.dev — marketplace listings

## Project Structure

```text
CarMarketAnalyzer/
├── app/
│   ├── main.py
│   ├── models/
│   │   └── vehicle.py
│   └── services/
│       ├── auto_dev_service.py
│       ├── market_service.py
│       ├── nhtsa_service.py
│       ├── pricing_service.py
│       └── vehicles_dev_service.py
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.tsx
│   ├── .env.example
│   ├── package.json
│   └── vite.config.ts
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## How the Valuation Works

Car Market Analyzer does not simply average all available listings.

The backend:

1. Decodes the VIN to identify the vehicle.
2. Searches configured marketplace providers.
3. Removes invalid or suspicious listing data.
4. Excludes the subject VIN from its own comparable set.
5. Scores each comparable vehicle based on trim, mileage, year, provider, and data quality.
6. Selects the strongest comparable vehicles.
7. Applies outlier filtering when enough comparable listings are available.
8. Calculates weighted market pricing.
9. Produces a retail estimate, purchase range, trade-in range, and confidence level.

This allows higher-quality comparable vehicles to influence the result more than loosely related listings.

## Local Development

### 1. Clone the repository

```bash
git clone https://github.com/OsmanSafi/CarMarketAnalyzer.git
cd CarMarketAnalyzer
```

### 2. Create the Python virtual environment

Windows PowerShell:

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Install backend dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure backend environment variables

Copy:

```text
.env.example
```

to:

```text
.env
```

Then add valid provider credentials:

```env
AUTO_DEV_API_KEY=your_auto_dev_api_key
VEHICLES_DEV_API_KEY=your_vehicles_dev_api_key
```

Do not commit the real `.env` file.

### 5. Start the backend

```powershell
python -m uvicorn app.main:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

Swagger API documentation:

```text
http://127.0.0.1:8000/docs
```

### 6. Install frontend dependencies

Open a second terminal:

```powershell
cd frontend
npm install
```

### 7. Configure the frontend

Copy:

```text
frontend/.env.example
```

to:

```text
frontend/.env
```

Local configuration:

```env
VITE_API_URL=http://127.0.0.1:8000
```

### 8. Start the frontend

```powershell
npm run dev
```

Frontend:

```text
http://localhost:5173
```

## API Endpoints

### Health / App Info

```http
GET /
```

### Decode VIN

```http
GET /vin/{vin}
```

### Analyze a Vehicle by Attributes

```http
GET /car
```

Parameters include:

- year
- make
- model
- trim
- mileage
- ZIP code

### Full VIN Valuation

```http
GET /valuation
```

Parameters:

- VIN
- mileage
- ZIP code

Example:

```text
/valuation?vin=SHHFK7H91JU426197&mileage=105000&zip_code=93960
```

## Example Output

A valuation can include:

- decoded vehicle details
- estimated market value
- fair purchase range
- estimated trade-in range
- valuation confidence
- marketplace listing count
- selected comparable count
- invalid listing count
- top comparable vehicles

## Data Quality

Marketplace data can contain malformed prices, duplicate vehicles, incomplete listings, or unrelated trims.

The application currently applies:

- minimum and maximum price validation
- year validation
- mileage validation
- market-relative price sanity checks
- VIN deduplication
- subject VIN exclusion
- comparable scoring
- price outlier filtering

## Trade-In Estimate

Trade value is currently modeled from the estimated retail value by reserving amounts for:

- dealer margin
- expected reconditioning
- vehicle age
- uncertainty

It is an analytical estimate and is not presented as direct wholesale or auction data.

## Limitations

The current MVP has several known limitations:

- marketplace coverage depends on available third-party APIs
- some vehicles may not have enough comparable data for a reliable valuation
- national listings may appear when local inventory is limited
- geographic weighting is not yet fully implemented
- estimated trade values are modeled rather than sourced from wholesale auction feeds

These areas are part of the planned roadmap.

## Roadmap

Planned improvements include:

- local-radius and geographic weighting
- distance-aware comparable scoring
- broader marketplace coverage
- dealer and private-party differentiation
- market trend analysis
- price-vs-mileage charts
- deal-quality labels
- regional pricing comparisons
- vehicle history integration
- production hosting
- automated tests
- CI/CD
- expanded documentation

## Security

Real API credentials are stored only in local or deployment environment variables.

The following files are intentionally excluded from Git:

```text
.env
frontend/.env
```

Safe templates are included:

```text
.env.example
frontend/.env.example
```

Frontend environment variables must never contain provider API secrets because Vite variables are exposed to the browser.

## Author

**Osman Safi**

GitHub: [OsmanSafi](https://github.com/OsmanSafi)

## License

No license has been added yet.
