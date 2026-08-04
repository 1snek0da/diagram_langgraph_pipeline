"""Stock technical pattern, support, and resistance node."""

from __future__ import annotations

from typing import Any

from ..analysis.market_metrics import normalize_bars
from ..analysis.technical_scoring import (
    combine_technical_scores,
    score_technical_pattern,
)
from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    analysis = state.get("stock_market_data_analysis", {})
    bars = normalize_bars(
        state.get("stock_market_data", {}).get("stock", {}).get("bars", [])
    )
    ma = analysis.get("ma_status", {})
    positions = [
        ma.get(f"ma{window}", {}).get("price_position") for window in (5, 10, 20, 60)
    ]
    if positions and all(position == "above" for position in positions):
        trend = "up"
    elif positions and all(position == "below" for position in positions):
        trend = "down"
    else:
        trend = "sideways"

    recent = bars[-60:]
    lows = [row["low"] for row in recent if row.get("low") is not None]
    highs = [row["high"] for row in recent if row.get("high") is not None]
    latest = analysis.get("latest_close")
    distance_ma20 = ma.get("ma20", {}).get("distance_pct")
    high_position_risk = distance_ma20 is not None and distance_ma20 > 0.15
    trend_scoring = analysis.get("trend_scoring", {})
    pattern_scoring = score_technical_pattern(bars)
    composite_scoring = combine_technical_scores(
        trend_scoring.get("score"), pattern_scoring.get("score")
    )
    return {
        "stock_technical_result": {
            "trend": trend,
            "support_price": round(min(lows), 4) if lows else None,
            "resistance_price": round(max(highs), 4) if highs else None,
            "latest_close": latest,
            "volume_signal": analysis.get("volume_price_signal", {}).get("signal"),
            "pattern_name": (
                "均线多头"
                if trend == "up"
                else "均线空头" if trend == "down" else "均线分化"
            ),
            "high_position_risk": high_position_risk,
            "abnormal_events": analysis.get("abnormal_events", []),
            "trend_scoring": trend_scoring,
            "pattern_scoring": pattern_scoring,
            "composite_scoring": composite_scoring,
            "missing_items": list(
                dict.fromkeys(
                    [
                        *trend_scoring.get("missing_items", []),
                        *pattern_scoring.get("missing_items", []),
                    ]
                )
            ),
        }
    }
