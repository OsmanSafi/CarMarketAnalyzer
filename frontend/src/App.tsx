import { useState } from "react";
import type { FormEvent } from "react";

import "./App.css";

type Comparable = {
  score: number;
  provider: string;
  vin: string | null;
  year: number | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  price: number;
  mileage: number | null;
  city: string | null;
  state: string | null;
  listing_url: string | null;
};

type Vehicle = {
  vin: string;
  year: number;
  make: string;
  model: string;
  trim: string | null;
  mileage: number;
  zip_code: string;
};

type MarketAnalysis = {
  estimated_market_value: number | null;

  fair_purchase_range: {
    low: number;
    high: number;
  } | null;

  estimated_trade_range: {
    low: number;
    high: number;
    midpoint: number;
  } | null;

  confidence: string;
  selected_comparable_count: number;
  raw_listing_count: number;
  validated_listing_count: number;
  invalid_listings_removed: number;
  warning: string | null;
  top_comparables: Comparable[];
};

type ValuationResponse = {
  vehicle: Vehicle;
  market_analysis: MarketAnalysis;
};

type ValidationErrors = {
  vin?: string;
  mileage?: string;
  zipCode?: string;
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

function currency(
  value: number | null | undefined,
) {
  if (value == null) {
    return "N/A";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatMileage(
  value: number | null | undefined,
) {
  if (value == null) {
    return "N/A";
  }

  return new Intl.NumberFormat(
    "en-US",
  ).format(value);
}

function validateForm(
  vin: string,
  mileage: string,
  zipCode: string,
): ValidationErrors {
  const errors: ValidationErrors = {};

  const normalizedVin = vin
    .trim()
    .toUpperCase();

  const vinPattern =
    /^[A-HJ-NPR-Z0-9]{17}$/;

  if (!normalizedVin) {
    errors.vin = "VIN is required.";
  } else if (
    !vinPattern.test(normalizedVin)
  ) {
    errors.vin =
      "Enter a valid 17-character VIN.";
  }

  const mileageNumber = Number(mileage);

  if (!mileage.trim()) {
    errors.mileage =
      "Mileage is required.";
  } else if (
    !Number.isInteger(mileageNumber) ||
    mileageNumber < 0
  ) {
    errors.mileage =
      "Enter a valid mileage.";
  } else if (mileageNumber > 500000) {
    errors.mileage =
      "Mileage must be 500,000 or less.";
  }

  if (!/^\d{5}$/.test(zipCode.trim())) {
    errors.zipCode =
      "Enter a valid 5-digit ZIP code.";
  }

  return errors;
}

async function getApiError(
  response: Response,
) {
  try {
    const body: {
      detail?:
      | string
      | Array<{ msg?: string }>;
    } = await response.json();

    if (typeof body.detail === "string") {
      return body.detail;
    }

    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => item.msg)
        .filter(Boolean)
        .join(", ");
    }

    return "Unable to analyze vehicle.";
  } catch {
    return "Unable to analyze vehicle.";
  }
}

function App() {
  const [vin, setVin] = useState("");
  const [miles, setMiles] = useState("");
  const [zipCode, setZipCode] =
    useState("");

  const [result, setResult] =
    useState<ValuationResponse | null>(
      null,
    );

  const [
    validationErrors,
    setValidationErrors,
  ] = useState<ValidationErrors>({});

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const errors = validateForm(
      vin,
      miles,
      zipCode,
    );

    setValidationErrors(errors);

    if (Object.keys(errors).length > 0) {
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const params =
        new URLSearchParams({
          vin: vin
            .trim()
            .toUpperCase(),
          mileage: miles.trim(),
          zip_code: zipCode.trim(),
        });

      const response = await fetch(
        `${API_URL}/valuation?${params.toString()}`,
      );

      if (!response.ok) {
        const message =
          await getApiError(response);

        throw new Error(message);
      }

      const data =
        (await response.json()) as ValuationResponse;

      setResult(data);
    } catch (err) {
      if (err instanceof TypeError) {
        setError(
          "The valuation service could not be reached. Make sure the backend is running.",
        );
      } else if (
        err instanceof Error
      ) {
        setError(err.message);
      } else {
        setError(
          "Something went wrong while analyzing the vehicle.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  const analysis =
    result?.market_analysis;

  const vehicle = result?.vehicle;

  const hasMarketValue =
    analysis?.estimated_market_value !=
    null &&
    analysis.selected_comparable_count >
    0;

  return (
    <main className="app-shell">
      <header className="navbar">
        <div className="brand">
          <div className="brand-mark">
            C
          </div>

          <div>
            <strong>
              Car Market Analyzer
            </strong>

            <span>
              Vehicle pricing
              intelligence
            </span>
          </div>
        </div>

        <div className="api-status">
          <span className="status-dot" />

          Market data connected
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">
            Automotive market
            intelligence
          </p>

          <h1>
            Know what a car is
            <span> actually worth.</span>
          </h1>

          <p className="hero-description">
            Decode a VIN, analyze
            marketplace listings, compare
            similar vehicles, and estimate
            fair retail and trade-in value.
          </p>
        </div>

        <form
          className="search-card"
          onSubmit={handleSubmit}
          noValidate
        >
          <div className="search-header">
            <div>
              <p className="card-label">
                Vehicle valuation
              </p>

              <h2>
                Analyze a vehicle
              </h2>
            </div>

            <span className="beta-badge">
              BETA
            </span>
          </div>

          <label>
            VIN

            <input
              value={vin}
              onChange={(event) => {
                setVin(
                  event.target.value
                    .toUpperCase(),
                );

                setValidationErrors(
                  (current) => ({
                    ...current,
                    vin: undefined,
                  }),
                );
              }}
              placeholder="17-character VIN"
              maxLength={17}
              className={
                validationErrors.vin
                  ? "input-error"
                  : ""
              }
            />

            {validationErrors.vin && (
              <span className="field-error">
                {validationErrors.vin}
              </span>
            )}
          </label>

          <div className="field-grid">
            <label>
              Mileage

              <input
                type="number"
                value={miles}
                onChange={(event) => {
                  setMiles(
                    event.target.value,
                  );

                  setValidationErrors(
                    (current) => ({
                      ...current,
                      mileage: undefined,
                    }),
                  );
                }}
                placeholder="105000"
                min="0"
                className={
                  validationErrors.mileage
                    ? "input-error"
                    : ""
                }
              />

              {validationErrors.mileage && (
                <span className="field-error">
                  {
                    validationErrors.mileage
                  }
                </span>
              )}
            </label>

            <label>
              ZIP code

              <input
                value={zipCode}
                onChange={(event) => {
                  const value =
                    event.target.value.replace(
                      /\D/g,
                      "",
                    );

                  setZipCode(value);

                  setValidationErrors(
                    (current) => ({
                      ...current,
                      zipCode: undefined,
                    }),
                  );
                }}
                placeholder="93960"
                maxLength={5}
                inputMode="numeric"
                className={
                  validationErrors.zipCode
                    ? "input-error"
                    : ""
                }
              />

              {validationErrors.zipCode && (
                <span className="field-error">
                  {
                    validationErrors.zipCode
                  }
                </span>
              )}
            </label>
          </div>

          <button
            className="analyze-button"
            type="submit"
            disabled={loading}
          >
            {loading
              ? "Analyzing market..."
              : "Analyze vehicle"}
          </button>

          <p className="search-note">
            Estimates are based on
            available marketplace data and
            comparable vehicle listings.
          </p>
        </form>
      </section>

      {loading && (
        <section className="loading-card">
          <div className="loader" />

          <div>
            <strong>
              Analyzing vehicle
            </strong>

            <p>
              Decoding the VIN, searching
              market listings, and scoring
              comparable vehicles.
            </p>
          </div>
        </section>
      )}

      {error && (
        <section className="error-card">
          <strong>
            Unable to analyze vehicle
          </strong>

          <p>{error}</p>
        </section>
      )}

      {result &&
        analysis &&
        vehicle &&
        !hasMarketValue && (
          <section className="no-data-card">
            <p className="eyebrow">
              Vehicle identified
            </p>

            <h2>
              {vehicle.year}{" "}
              {vehicle.make}{" "}
              {vehicle.model}
            </h2>

            <p className="no-data-trim">
              {vehicle.trim ||
                "Trim unavailable"}{" "}
              ·{" "}
              {formatMileage(
                vehicle.mileage,
              )}{" "}
              miles
            </p>

            <div className="no-data-message">
              <strong>
                Not enough comparable
                market data
              </strong>

              <p>
                We successfully decoded
                this vehicle, but there
                aren't enough similar
                listings available right
                now to generate a reliable
                valuation.
              </p>

              {analysis.warning && (
                <small>
                  {analysis.warning}
                </small>
              )}
            </div>
          </section>
        )}

      {result &&
        analysis &&
        vehicle &&
        hasMarketValue && (
          <section className="results">
            <div className="vehicle-heading">
              <div>
                <p className="eyebrow">
                  Valuation result
                </p>

                <h2>
                  {vehicle.year}{" "}
                  {vehicle.make}{" "}
                  {vehicle.model}
                </h2>

                <p>
                  {vehicle.trim ||
                    "Unknown trim"}{" "}
                  ·{" "}
                  {formatMileage(
                    vehicle.mileage,
                  )}{" "}
                  miles · ZIP{" "}
                  {vehicle.zip_code}
                </p>
              </div>

              <div
                className={`confidence confidence-${analysis.confidence}`}
              >
                {analysis.confidence}{" "}
                confidence
              </div>
            </div>

            <div className="value-grid">
              <article className="value-card primary">
                <span>
                  Estimated market value
                </span>

                <strong>
                  {currency(
                    analysis.estimated_market_value,
                  )}
                </strong>

                <small>
                  Based on{" "}
                  {
                    analysis.selected_comparable_count
                  }{" "}
                  selected comparables
                </small>
              </article>

              <article className="value-card">
                <span>
                  Fair purchase range
                </span>

                <strong>
                  {analysis.fair_purchase_range
                    ? `${currency(
                      analysis
                        .fair_purchase_range
                        .low,
                    )} – ${currency(
                      analysis
                        .fair_purchase_range
                        .high,
                    )}`
                    : "N/A"}
                </strong>

                <small>
                  Suggested retail buying
                  range
                </small>
              </article>

              <article className="value-card">
                <span>
                  Estimated trade value
                </span>

                <strong>
                  {analysis.estimated_trade_range
                    ? currency(
                      analysis
                        .estimated_trade_range
                        .midpoint,
                    )
                    : "N/A"}
                </strong>

                <small>
                  {analysis.estimated_trade_range
                    ? `${currency(
                      analysis
                        .estimated_trade_range
                        .low,
                    )} – ${currency(
                      analysis
                        .estimated_trade_range
                        .high,
                    )}`
                    : ""}
                </small>
              </article>
            </div>

            <div className="market-summary">
              <div>
                <strong>
                  {
                    analysis.raw_listing_count
                  }
                </strong>

                <span>
                  Market listings scanned
                </span>
              </div>

              <div>
                <strong>
                  {
                    analysis.selected_comparable_count
                  }
                </strong>

                <span>
                  Strong comparables used
                </span>
              </div>

              <div>
                <strong>
                  {
                    analysis.invalid_listings_removed
                  }
                </strong>

                <span>
                  Invalid listings removed
                </span>
              </div>
            </div>

            <div className="comparables-section">
              <div className="section-heading">
                <p className="eyebrow">
                  Comparable vehicles
                </p>

                <h2>
                  Top market matches
                </h2>
              </div>

              <div className="comparables-grid">
                {analysis.top_comparables.map(
                  (comp) => (
                    <article
                      className="comparable-card"
                      key={
                        comp.vin ??
                        `${comp.year}-${comp.price}-${comp.mileage}`
                      }
                    >
                      <div className="comp-top">
                        <div>
                          <strong>
                            {comp.year}{" "}
                            {comp.make}{" "}
                            {comp.model}
                          </strong>

                          <span>
                            {comp.trim ||
                              "Unknown trim"}
                          </span>
                        </div>

                        <div className="match-score">
                          {comp.score}
                        </div>
                      </div>

                      <div className="comp-price">
                        {currency(
                          comp.price,
                        )}
                      </div>

                      <div className="comp-details">
                        <span>
                          {formatMileage(
                            comp.mileage,
                          )}{" "}
                          mi
                        </span>

                        <span>
                          {comp.city &&
                            comp.state
                            ? `${comp.city}, ${comp.state}`
                            : "Location unavailable"}
                        </span>
                      </div>

                      {comp.listing_url && (
                        <a
                          href={
                            comp.listing_url
                          }
                          target="_blank"
                          rel="noreferrer"
                        >
                          View listing
                        </a>
                      )}
                    </article>
                  ),
                )}
              </div>
            </div>
          </section>
        )}
    </main>
  );
}

export default App;