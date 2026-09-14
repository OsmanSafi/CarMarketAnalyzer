from statistics import mean


def build_valuation_consensus(
    internal_value: float | None,
    internal_confidence: str,
    marketcheck_value: float | None,
) -> dict:
    sources = []

    if internal_value is not None and internal_value > 0:
        sources.append(
            {
                "source": "internal_market_model",
                "value": float(internal_value),
            }
        )

    if marketcheck_value is not None and marketcheck_value > 0:
        sources.append(
            {
                "source": "marketcheck",
                "value": float(marketcheck_value),
            }
        )

    if not sources:
        return {
            "consensus_value": None,
            "source_count": 0,
            "sources": [],
            "spread": None,
            "spread_percent": None,
            "confidence": "low",
        }

    values = [source["value"] for source in sources]

    consensus_value = mean(values)

    spread = max(values) - min(values) if len(values) > 1 else 0.0

    spread_percent = spread / consensus_value * 100 if consensus_value > 0 else 0.0

    if len(values) == 1:
        consensus_confidence = "low"

    elif spread_percent <= 5 and internal_confidence in {"high", "medium"}:
        consensus_confidence = "high"

    elif spread_percent <= 10 and internal_confidence in {"high", "medium"}:
        consensus_confidence = "medium"

    else:
        consensus_confidence = "low"

    return {
        "consensus_value": round(
            consensus_value,
            2,
        ),
        "source_count": len(sources),
        "sources": [
            {
                **source,
                "value": round(
                    source["value"],
                    2,
                ),
            }
            for source in sources
        ],
        "spread": round(
            spread,
            2,
        ),
        "spread_percent": round(
            spread_percent,
            2,
        ),
        "confidence": consensus_confidence,
        "method": "simple_multi_source_average",
    }
