import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import "./App.css";

type Mode = "buy" | "trade";

type Comparable = {
  score: number;
  provider: string;
  vin: string | null;
  year: number | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  raw_price?: number;
  adjusted_price?: number;
  price?: number;
  mileage: number | null;
  days_on_market?: number | null;
  city: string | null;
  state: string | null;
  listing_url: string | null;
  image_url?: string | null;
};

type Vehicle = {
  vin: string;
  year: number;
  make: string;
  model: string;
  trim: string | null;
  mileage: number;
  zip_code: string;
  state?: string | null;
  image_url?: string | null;
};

type MarketAnalysis = {
  comparable_market_value?: number | null;
  estimated_market_value?: number | null;

  fair_purchase_value?: number | null;

  fair_purchase_range?: {
    low: number;
    high: number;
  } | null;

  asking_price_analysis?: {
    asking_price: number;
    difference_from_fair_market?: number | null;
    difference_from_fair_purchase?: number | null;
  } | null;

  confidence: string;
  selected_comparable_count: number;
  raw_listing_count: number;
  validated_listing_count?: number;
  invalid_listings_removed: number;

  providers_used?: number;
  warning: string | null;

  top_comparables: Comparable[];
};

type ValuationConsensus = {
  fair_market_value: number | null;
  source_count: number;
  agreement: string;
  confidence: string;

  source_range?: {
    low: number;
    high: number;
  } | null;
};

type TradeValuation = {
  estimated_trade_value: number | null;

  trade_range?: {
    low: number;
    high: number;
  } | null;

  best_actual_offer?: {
    source?: string;
    value?: number;
  } | null;

  source_count: number;
  actual_offer_count: number;
  confidence: string;
};

type ValuationResponse = {
  vehicle: Vehicle;
  market_analysis: MarketAnalysis;

  valuation_consensus?: ValuationConsensus | null;

  trade_valuation?: TradeValuation | null;

  listing_inputs?: {
    asking_price?: number | null;
    days_on_market?: number | null;
  };

  trade_inputs?: {
    carmax_offer?: number | null;
    carvana_offer?: number | null;
    dealer_offer?: number | null;
  };
};

type ValidationErrors = {
  vin?: string;
  mileage?: string;
  zipCode?: string;
  dealerValue?: string;
};

const API_URL =
  import.meta.env.VITE_API_URL ??
  "http://127.0.0.1:8000";

function currency(
  value: number | null | undefined,
) {
  if (value == null) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function number(
  value: number | null | undefined,
) {
  if (value == null) {
    return "—";
  }

  return new Intl.NumberFormat(
    "en-US",
  ).format(value);
}

function validateCommonFields(
  vin: string,
  mileage: string,
  zipCode: string,
  dealerValue: string,
): ValidationErrors {
  const errors: ValidationErrors = {};

  const normalizedVin = vin
    .trim()
    .toUpperCase();

  if (
    !/^[A-HJ-NPR-Z0-9]{17}$/.test(
      normalizedVin,
    )
  ) {
    errors.vin =
      "Enter a valid 17-character VIN.";
  }

  const mileageNumber = Number(mileage);

  if (
    mileage.trim() === "" ||
    !Number.isInteger(mileageNumber) ||
    mileageNumber < 0 ||
    mileageNumber > 500000
  ) {
    errors.mileage =
      "Enter a valid mileage.";
  }

  if (!/^\d{5}$/.test(zipCode.trim())) {
    errors.zipCode =
      "Enter a valid 5-digit ZIP code.";
  }

  const offer = Number(dealerValue);

  if (
    dealerValue.trim() === "" ||
    !Number.isFinite(offer) ||
    offer <= 0
  ) {
    errors.dealerValue =
      "Enter the dealer's offer.";
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
  } catch {
    // Fall through to default.
  }

  return "Unable to analyze this vehicle.";
}

type PricePosition = {
  label: string;
  tone: "good" | "fair" | "high";
  percent: number;
};

function getPurchasePricePosition(
  dealerPrice: number | null,
  range:
    | {
      low: number;
      high: number;
    }
    | null,
): PricePosition | null {
  if (
    dealerPrice == null ||
    range == null ||
    range.low <= 0 ||
    range.high <= range.low
  ) {
    return null;
  }

  const width = range.high - range.low;

  const scaleLow = Math.max(
    0,
    range.low - width,
  );

  const scaleHigh =
    range.high + width;

  const rawPercent =
    ((dealerPrice - scaleLow) /
      (scaleHigh - scaleLow)) *
    100;

  const percent = Math.min(
    100,
    Math.max(0, rawPercent),
  );

  if (dealerPrice < range.low) {
    return {
      label: "Strong price",
      tone: "good",
      percent,
    };
  }

  if (dealerPrice <= range.high) {
    return {
      label: "Fair price",
      tone: "fair",
      percent,
    };
  }

  return {
    label: "Above fair range",
    tone: "high",
    percent,
  };
}

function getTradePricePosition(
  dealerOffer: number | null,
  range:
    | {
      low: number;
      high: number;
    }
    | null,
): PricePosition | null {
  if (
    dealerOffer == null ||
    range == null ||
    range.low <= 0 ||
    range.high <= range.low
  ) {
    return null;
  }

  const width = range.high - range.low;

  const scaleLow = Math.max(
    0,
    range.low - width,
  );

  const scaleHigh =
    range.high + width;

  const rawPercent =
    ((dealerOffer - scaleLow) /
      (scaleHigh - scaleLow)) *
    100;

  const percent = Math.min(
    100,
    Math.max(0, rawPercent),
  );

  if (dealerOffer < range.low) {
    return {
      label: "Low offer",
      tone: "high",
      percent,
    };
  }

  if (dealerOffer <= range.high) {
    return {
      label: "Fair offer",
      tone: "fair",
      percent,
    };
  }

  return {
    label: "Strong offer",
    tone: "good",
    percent,
  };
}

function App() {
  const [mode, setMode] =
    useState<Mode>("buy");

  const [vin, setVin] = useState("");
  const [mileage, setMileage] =
    useState("");
  const [zipCode, setZipCode] =
    useState("");

  const [
    dealerValue,
    setDealerValue,
  ] = useState("");

  const [
    daysOnMarket,
    setDaysOnMarket,
  ] = useState("");

  const [
    carmaxOffer,
    setCarmaxOffer,
  ] = useState("");

  const [
    carvanaOffer,
    setCarvanaOffer,
  ] = useState("");

  const [
    result,
    setResult,
  ] =
    useState<ValuationResponse | null>(
      null,
    );

  const [
    validationErrors,
    setValidationErrors,
  ] =
    useState<ValidationErrors>({});

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  function resetResults() {
    setResult(null);
    setError("");
    setValidationErrors({});
  }

  function changeMode(
    nextMode: Mode,
  ) {
    setMode(nextMode);
    resetResults();
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const errors =
      validateCommonFields(
        vin,
        mileage,
        zipCode,
        dealerValue,
      );

    setValidationErrors(errors);

    if (
      Object.keys(errors).length > 0
    ) {
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
          mileage: mileage.trim(),
          zip_code: zipCode.trim(),
        });

      if (mode === "buy") {
        params.set(
          "asking_price",
          dealerValue.trim(),
        );

        if (daysOnMarket.trim()) {
          params.set(
            "days_on_market",
            daysOnMarket.trim(),
          );
        }
      } else {
        params.set(
          "dealer_offer",
          dealerValue.trim(),
        );

        if (carmaxOffer.trim()) {
          params.set(
            "carmax_offer",
            carmaxOffer.trim(),
          );
        }

        if (carvanaOffer.trim()) {
          params.set(
            "carvana_offer",
            carvanaOffer.trim(),
          );
        }
      }

      const response = await fetch(
        `${API_URL}/valuation?${params.toString()}`,
      );

      if (!response.ok) {
        throw new Error(
          await getApiError(response),
        );
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

  const marketValue = useMemo(() => {
    if (!result) {
      return null;
    }

    return (
      result.valuation_consensus
        ?.fair_market_value ??
      result.market_analysis
        .comparable_market_value ??
      result.market_analysis
        .estimated_market_value ??
      null
    );
  }, [result]);

  const fairPurchaseValue =
    result?.market_analysis
      .fair_purchase_value ?? null;

  const tradeValue =
    result?.trade_valuation
      ?.estimated_trade_value ?? null;

  const dealerNumber =
    dealerValue.trim()
      ? Number(dealerValue)
      : null;

  const purchaseGap =
    mode === "buy" &&
      dealerNumber != null &&
      fairPurchaseValue != null
      ? dealerNumber -
      fairPurchaseValue
      : null;

  const tradeGap =
    mode === "trade" &&
      dealerNumber != null &&
      tradeValue != null
      ? dealerNumber - tradeValue
      : null;

  const purchaseRange =
    result?.market_analysis
      .fair_purchase_range ?? null;

  const tradeRange =
    result?.trade_valuation
      ?.trade_range ?? null;

  const pricePosition =
    mode === "buy"
      ? getPurchasePricePosition(
        dealerNumber,
        purchaseRange,
      )
      : getTradePricePosition(
        dealerNumber,
        tradeRange,
      );

  const topComparables =
    result?.market_analysis
      .top_comparables ?? [];

  return (
    <div className="site-shell">
      <header className="site-header">
        <div className="header-inner">
          <div className="brand">
            <div className="brand-symbol">
              CM
            </div>

            <div>
              <strong>
                Car Market Analyzer
              </strong>

              <span>
                Deal intelligence
              </span>
            </div>
          </div>

          <div className="header-meta">
            Independent market analysis
          </div>
        </div>
      </header>

      <main className="page">
        <section className="intro">
          <div className="intro-copy">
            <p className="section-kicker">
              Deal analysis
            </p>

            <h1>
              Know the numbers before
              you negotiate.
            </h1>

            <p>
              Compare a dealer's offer
              against current market
              evidence before you sign.
            </p>
          </div>
        </section>

        <section className="workspace">
          <aside className="analysis-panel">
            <div className="mode-switch">
              <button
                type="button"
                className={
                  mode === "buy"
                    ? "mode-button active"
                    : "mode-button"
                }
                onClick={() =>
                  changeMode("buy")
                }
              >
                Buying
              </button>

              <button
                type="button"
                className={
                  mode === "trade"
                    ? "mode-button active"
                    : "mode-button"
                }
                onClick={() =>
                  changeMode("trade")
                }
              >
                Trading in
              </button>
            </div>

            <div className="panel-heading">
              <h2>
                {mode === "buy"
                  ? "Analyze a purchase"
                  : "Analyze a trade offer"}
              </h2>

              <p>
                {mode === "buy"
                  ? "Enter the vehicle and the price the dealer is asking."
                  : "Enter your vehicle and the trade value the dealer offered."}
              </p>
            </div>

            <form
              onSubmit={handleSubmit}
              noValidate
              className="valuation-form"
            >
              <label>
                <span>VIN</span>

                <input
                  value={vin}
                  maxLength={17}
                  placeholder="17-character VIN"
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
                  className={
                    validationErrors.vin
                      ? "invalid"
                      : ""
                  }
                />

                {validationErrors.vin && (
                  <small className="field-error">
                    {
                      validationErrors.vin
                    }
                  </small>
                )}
              </label>

              <div className="form-row">
                <label>
                  <span>Mileage</span>

                  <input
                    type="number"
                    min="0"
                    value={mileage}
                    placeholder="75000"
                    onChange={(
                      event,
                    ) => {
                      setMileage(
                        event.target.value,
                      );

                      setValidationErrors(
                        (current) => ({
                          ...current,
                          mileage:
                            undefined,
                        }),
                      );
                    }}
                    className={
                      validationErrors.mileage
                        ? "invalid"
                        : ""
                    }
                  />

                  {validationErrors.mileage && (
                    <small className="field-error">
                      {
                        validationErrors.mileage
                      }
                    </small>
                  )}
                </label>

                <label>
                  <span>ZIP code</span>

                  <input
                    value={zipCode}
                    maxLength={5}
                    inputMode="numeric"
                    placeholder="93960"
                    onChange={(
                      event,
                    ) => {
                      setZipCode(
                        event.target.value.replace(
                          /\D/g,
                          "",
                        ),
                      );

                      setValidationErrors(
                        (current) => ({
                          ...current,
                          zipCode:
                            undefined,
                        }),
                      );
                    }}
                    className={
                      validationErrors.zipCode
                        ? "invalid"
                        : ""
                    }
                  />

                  {validationErrors.zipCode && (
                    <small className="field-error">
                      {
                        validationErrors.zipCode
                      }
                    </small>
                  )}
                </label>
              </div>

              <label>
                <span>
                  {mode === "buy"
                    ? "Dealer asking price"
                    : "Dealer trade offer"}
                </span>

                <div className="money-input">
                  <span>$</span>

                  <input
                    type="number"
                    min="0"
                    value={dealerValue}
                    placeholder={
                      mode === "buy"
                        ? "28000"
                        : "15000"
                    }
                    onChange={(
                      event,
                    ) => {
                      setDealerValue(
                        event.target.value,
                      );

                      setValidationErrors(
                        (current) => ({
                          ...current,
                          dealerValue:
                            undefined,
                        }),
                      );
                    }}
                  />
                </div>

                {validationErrors.dealerValue && (
                  <small className="field-error">
                    {
                      validationErrors.dealerValue
                    }
                  </small>
                )}
              </label>

              {mode === "buy" ? (
                <label>
                  <span>
                    Days on market
                    <em>Optional</em>
                  </span>

                  <input
                    type="number"
                    min="0"
                    value={daysOnMarket}
                    placeholder="50"
                    onChange={(
                      event,
                    ) =>
                      setDaysOnMarket(
                        event.target.value,
                      )
                    }
                  />
                </label>
              ) : (
                <div className="optional-offers">
                  <div className="optional-heading">
                    <strong>
                      Other offers
                    </strong>

                    <span>
                      Optional
                    </span>
                  </div>

                  <div className="form-row">
                    <label>
                      <span>
                        CarMax offer
                      </span>

                      <div className="money-input">
                        <span>$</span>

                        <input
                          type="number"
                          min="0"
                          value={
                            carmaxOffer
                          }
                          placeholder="15400"
                          onChange={(
                            event,
                          ) =>
                            setCarmaxOffer(
                              event.target
                                .value,
                            )
                          }
                        />
                      </div>
                    </label>

                    <label>
                      <span>
                        Carvana offer
                      </span>

                      <div className="money-input">
                        <span>$</span>

                        <input
                          type="number"
                          min="0"
                          value={
                            carvanaOffer
                          }
                          placeholder="15800"
                          onChange={(
                            event,
                          ) =>
                            setCarvanaOffer(
                              event.target
                                .value,
                            )
                          }
                        />
                      </div>
                    </label>
                  </div>
                </div>
              )}

              <button
                type="submit"
                className="primary-button"
                disabled={loading}
              >
                {loading
                  ? "Analyzing..."
                  : "Analyze offer"}
              </button>

              <p className="form-disclaimer">
                Estimates are based on
                available market data and
                are not dealer records or
                guaranteed transaction
                prices.
              </p>
            </form>
          </aside>

          <section className="results-panel">
            {!result &&
              !loading &&
              !error && (
                <div className="empty-state">
                  <div className="empty-rule" />

                  <span>
                    Market analysis
                  </span>

                  <h2>
                    Your deal analysis
                    will appear here.
                  </h2>

                  <p>
                    Enter the vehicle
                    information and the
                    dealer's offer to
                    compare it with
                    current market
                    evidence.
                  </p>
                </div>
              )}

            {loading && (
              <div className="loading-state">
                <div className="spinner" />

                <div>
                  <strong>
                    Analyzing market data
                  </strong>

                  <p>
                    Comparing the vehicle
                    with available
                    listings and
                    valuation sources.
                  </p>
                </div>
              </div>
            )}

            {error && (
              <div className="error-state">
                <strong>
                  Analysis unavailable
                </strong>

                <p>{error}</p>
              </div>
            )}

            {result && (
              <div className="results-content">
                <div className="vehicle-summary">
                  <div>
                    <p className="section-kicker">
                      Analysis
                    </p>

                    <h2>
                      {
                        result.vehicle
                          .year
                      }{" "}
                      {
                        result.vehicle
                          .make
                      }{" "}
                      {
                        result.vehicle
                          .model
                      }
                    </h2>

                    <p>
                      {result.vehicle
                        .trim ||
                        "Trim unavailable"}
                      {" · "}
                      {number(
                        result.vehicle
                          .mileage,
                      )}{" "}
                      miles
                    </p>
                  </div>

                  <div className="confidence-label">
                    {
                      result
                        .market_analysis
                        .confidence
                    }{" "}
                    confidence
                  </div>
                </div>

                {mode === "buy" ? (
                  <>
                    <div className="deal-summary">
                      <div className="main-number">
                        <span>
                          Dealer asking
                        </span>

                        <strong>
                          {currency(
                            dealerNumber,
                          )}
                        </strong>
                      </div>
                      {pricePosition && (
                        <div className="price-position">
                          <div className="price-position-heading">
                            <div>
                              <span>Price position</span>

                              <strong
                                className={`price-rank ${pricePosition.tone}`}
                              >
                                {pricePosition.label}
                              </strong>
                            </div>

                            <span>
                              Based on estimated fair range
                            </span>
                          </div>

                          <div className="price-scale">
                            <div className="price-scale-segments">
                              <span>Strong</span>
                              <span>Fair</span>
                              <span>
                                {mode === "buy"
                                  ? "High"
                                  : "Strong"}
                              </span>
                            </div>

                            <div className="price-track">
                              <div className="price-track-good" />
                              <div className="price-track-fair" />
                              <div className="price-track-high" />

                              <div
                                className="price-marker"
                                style={{
                                  left: `${pricePosition.percent}%`,
                                }}
                              >
                                <span />
                              </div>
                            </div>

                            <div className="price-scale-values">
                              <span>
                                {mode === "buy"
                                  ? purchaseRange
                                    ? currency(
                                      purchaseRange.low,
                                    )
                                    : "—"
                                  : tradeRange
                                    ? currency(
                                      tradeRange.low,
                                    )
                                    : "—"}
                              </span>

                              <strong>
                                Dealer:{" "}
                                {currency(dealerNumber)}
                              </strong>

                              <span>
                                {mode === "buy"
                                  ? purchaseRange
                                    ? currency(
                                      purchaseRange.high,
                                    )
                                    : "—"
                                  : tradeRange
                                    ? currency(
                                      tradeRange.high,
                                    )
                                    : "—"}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="comparison-numbers">
                        <div>
                          <span>
                            Fair market
                          </span>

                          <strong>
                            {currency(
                              marketValue,
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            Fair purchase
                            target
                          </span>

                          <strong>
                            {currency(
                              fairPurchaseValue,
                            )}
                          </strong>
                        </div>
                      </div>
                    </div>

                    {purchaseGap != null && (
                      <div
                        className={
                          purchaseGap > 0
                            ? "deal-message caution"
                            : "deal-message positive"
                        }
                      >
                        <strong>
                          {purchaseGap > 0
                            ? `${currency(
                              purchaseGap,
                            )} above the estimated fair purchase target`
                            : `${currency(
                              Math.abs(
                                purchaseGap,
                              ),
                            )} below the estimated fair purchase target`}
                        </strong>

                        <p>
                          {purchaseRange
                            ? `Current market evidence suggests a fair purchase range of ${currency(
                              purchaseRange.low,
                            )} to ${currency(
                              purchaseRange.high,
                            )}.`
                            : "The estimate is based on currently available market evidence."}
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="deal-summary">
                      <div className="main-number">
                        <span>
                          Dealer trade
                          offer
                        </span>

                        <strong>
                          {currency(
                            dealerNumber,
                          )}
                        </strong>
                      </div>

                      <div className="comparison-numbers">
                        <div>
                          <span>
                            Estimated
                            trade value
                          </span>

                          <strong>
                            {currency(
                              tradeValue,
                            )}
                          </strong>
                        </div>

                        <div>
                          <span>
                            Fair trade
                            range
                          </span>

                          <strong className="range-value">
                            {tradeRange
                              ? `${currency(
                                tradeRange.low,
                              )} – ${currency(
                                tradeRange.high,
                              )}`
                              : "—"}
                          </strong>
                        </div>
                      </div>
                    </div>

                    {tradeGap != null && (
                      <div
                        className={
                          tradeGap < 0
                            ? "deal-message caution"
                            : "deal-message positive"
                        }
                      >
                        <strong>
                          {tradeGap < 0
                            ? `${currency(
                              Math.abs(
                                tradeGap,
                              ),
                            )} below the estimated trade value`
                            : `${currency(
                              tradeGap,
                            )} above the estimated trade value`}
                        </strong>

                        <p>
                          Compare this
                          number with any
                          independent cash
                          offers before
                          accepting the
                          dealer's trade
                          value.
                        </p>
                      </div>
                    )}
                  </>
                )}

                <div className="evidence-section">
                  <div className="section-title-row">
                    <div>
                      <span>
                        Market evidence
                      </span>

                      <h3>
                        What supports this
                        estimate
                      </h3>
                    </div>
                  </div>

                  <div className="evidence-grid">
                    <div>
                      <strong>
                        {
                          result
                            .market_analysis
                            .raw_listing_count
                        }
                      </strong>

                      <span>
                        Listings reviewed
                      </span>
                    </div>

                    <div>
                      <strong>
                        {
                          result
                            .market_analysis
                            .selected_comparable_count
                        }
                      </strong>

                      <span>
                        Comparables used
                      </span>
                    </div>

                    <div>
                      <strong>
                        {result
                          .valuation_consensus
                          ?.source_count ??
                          1}
                      </strong>

                      <span>
                        Valuation sources
                      </span>
                    </div>

                    <div>
                      <strong className="capitalize">
                        {result
                          .valuation_consensus
                          ?.agreement ??
                          result
                            .market_analysis
                            .confidence}
                      </strong>

                      <span>
                        Source agreement
                      </span>
                    </div>
                  </div>
                </div>

                {topComparables.length >
                  0 && (
                    <div className="comparables-section">
                      <div className="section-title-row">
                        <div>
                          <span>
                            Comparables
                          </span>

                          <h3>
                            Closest market
                            matches
                          </h3>
                        </div>
                      </div>

                      <div className="comparables-table">
                        <div className="table-header">
                          <span>
                            Vehicle
                          </span>

                          <span>
                            Mileage
                          </span>

                          <span>
                            Price
                          </span>

                          <span>
                            Location
                          </span>
                        </div>

                        {topComparables
                          .slice(0, 6)
                          .map(
                            (
                              comparable,
                            ) => {
                              const price =
                                comparable.adjusted_price ??
                                comparable.raw_price ??
                                comparable.price ??
                                null;

                              return (
                                <div
                                  className="table-row"
                                  key={
                                    comparable.vin ??
                                    `${comparable.year}-${price}-${comparable.mileage}`
                                  }
                                >
                                  <div>
                                    <strong>
                                      {
                                        comparable.year
                                      }{" "}
                                      {
                                        comparable.make
                                      }{" "}
                                      {
                                        comparable.model
                                      }
                                    </strong>

                                    <span>
                                      {comparable.trim ||
                                        "Trim unavailable"}
                                    </span>
                                  </div>

                                  <span>
                                    {number(
                                      comparable.mileage,
                                    )}{" "}
                                    mi
                                  </span>

                                  <strong>
                                    {currency(
                                      price,
                                    )}
                                  </strong>

                                  <span>
                                    {comparable.city &&
                                      comparable.state
                                      ? `${comparable.city}, ${comparable.state}`
                                      : comparable.state ||
                                      "—"}
                                  </span>
                                </div>
                              );
                            },
                          )}
                      </div>
                    </div>
                  )}
              </div>
            )}
          </section>
        </section>
      </main>

      <footer className="site-footer">
        <span>
          Car Market Analyzer
        </span>

        <span>
          Independent estimates based
          on available market data.
        </span>
      </footer>
    </div>
  );
}

export default App;