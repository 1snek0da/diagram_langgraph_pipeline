"""Deterministic daily-bar scoring rules from ``输入输出.docx``.

The document mixes fully specified thresholds with a few qualitative labels.
This module implements the explicit thresholds and records the small number of
operational assumptions needed to turn qualitative labels into reproducible
calculations.  It never treats an incomplete score as a trading instruction.
"""

from __future__ import annotations

from statistics import mean
from typing import Any, Iterable

from .market_metrics import normalize_bars


def score_trend_system(raw_bars: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Score the 70-point MA system and 30-point volume system."""

    bars = normalize_bars(raw_bars)
    closes = [float(row["adj_close"]) for row in bars]
    volumes = [float(row["volume"]) for row in bars]
    missing: list[str] = []
    if len(bars) < 65:
        return {
            "score": None,
            "max_score": 100,
            "phase": "insufficient_data",
            "components": {},
            "missing_items": ["趋势评分至少需要65个交易日"],
            "formula_version": "input_output_trend_v1",
        }

    ma = {window: _trailing_mean(closes, window) for window in (5, 10, 20, 60)}
    previous_ma5 = _trailing_mean(closes[:-5], 5)
    previous_ma10 = _trailing_mean(closes[:-5], 10)
    previous_ma60 = _trailing_mean(closes[:-5], 60)
    phase = _detect_phase(bars, ma[60])
    if phase["name"] == "unclassified":
        missing.append("未落入文档定义的一波底部或一波后高位横盘阶段")

    divergence = abs(ma[5] - ma[10]) / ma[10]
    previous_divergence = abs(previous_ma5 - previous_ma10) / previous_ma10
    divergence_level = (
        "highly_converged"
        if divergence < 0.10
        else "lightly_converged" if divergence <= 0.20 else "diverged"
    )
    stage_scores = {
        "one_wave_bottom": {
            "highly_converged": 20,
            "lightly_converged": 15,
            "diverged": 10,
        },
        "high_consolidation": {
            "highly_converged": 25,
            "lightly_converged": 15,
            "diverged": 5,
        },
    }
    convergence_score = stage_scores.get(phase["name"], {}).get(divergence_level)
    change = divergence - previous_divergence
    direction = (
        "widening" if change > 0.001 else "narrowing" if change < -0.001 else "flat"
    )
    direction_score = {"widening": 15, "flat": 8, "narrowing": 3}[direction]
    alignment, alignment_score = _ma_alignment(ma, previous_ma60)
    price_relation, price_score = _price_ma_score(closes[-1], ma[10], ma[60])
    price_volume, price_volume_score = _price_volume_score(
        closes[-1], ma[5], volumes[-1], mean(volumes[-5:])
    )
    candle_pattern, candle_score = _candle_volume_score(
        bars[-1], bars[-2], mean(volumes[-5:])
    )

    component_scores = [
        convergence_score,
        direction_score,
        alignment_score,
        price_score,
        price_volume_score,
        candle_score,
    ]
    score = (
        sum(component_scores)
        if all(value is not None for value in component_scores)
        else None
    )
    return {
        "score": score,
        "max_score": 100,
        "ma_system_score": (
            convergence_score + direction_score + alignment_score + price_score
            if convergence_score is not None
            else None
        ),
        "volume_system_score": price_volume_score + candle_score,
        "phase": phase["name"],
        "phase_metrics": phase,
        "components": {
            "ma5_ma10_convergence": {
                "value": round(divergence, 6),
                "level": divergence_level,
                "score": convergence_score,
                "max_score": 25,
            },
            "convergence_direction": {
                "current": round(divergence, 6),
                "five_days_ago": round(previous_divergence, 6),
                "direction": direction,
                "score": direction_score,
                "max_score": 15,
            },
            "ma_alignment": {
                "status": alignment,
                "score": alignment_score,
                "max_score": 15,
            },
            "price_ma_relation": {
                "status": price_relation,
                "score": price_score,
                "max_score": 15,
            },
            "price_volume_relation": {
                "status": price_volume,
                "score": price_volume_score,
                "max_score": 20,
            },
            "candle_volume_pattern": {
                "status": candle_pattern,
                "score": candle_score,
                "max_score": 10,
            },
        },
        "ma_values": {f"ma{window}": round(value, 4) for window, value in ma.items()},
        "volume_ma": {
            "ma5": round(mean(volumes[-5:]), 4),
            "ma10": round(mean(volumes[-10:]), 4),
        },
        "missing_items": missing,
        "assumptions": [
            "均线偏离率方向以0.1个百分点作为持平容差",
            "大阳线/大阴线以实体占当日振幅不低于60%识别",
        ],
        "formula_version": "input_output_trend_v1",
    }


def score_technical_pattern(raw_bars: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Score breakout quality and the currently applicable entry point."""

    bars = normalize_bars(raw_bars)
    if len(bars) < 70:
        return {
            "score": None,
            "max_score": 10,
            "range": {"type": "insufficient_data"},
            "missing_items": ["技术形态评分至少需要70个交易日"],
            "formula_version": "input_output_pattern_v1",
        }

    range_info = _detect_range(bars)
    breakout = _find_recent_breakout(bars, range_info.get("duration", 20))
    if breakout is None:
        return {
            "score": None,
            "max_score": 10,
            "range": range_info,
            "breakout": None,
            "entry_point": {"type": "none", "score": None},
            "missing_items": ["未识别到收盘突破震荡区间上沿且当日涨幅大于5%的关键K线"],
            "formula_version": "input_output_pattern_v1",
        }

    breakout_index, upper = breakout
    quality = _breakout_quality(bars, breakout_index)
    entry = _entry_score(bars, breakout_index, upper)
    score = round(quality["score"] * 0.4 + entry["score"] * 0.6, 4)
    return {
        "score": score,
        "max_score": 10,
        "range": range_info,
        "breakout": {
            "date": bars[breakout_index]["trade_date"],
            "range_upper": round(upper, 4),
            **quality,
        },
        "entry_point": entry,
        "missing_items": [],
        "formula": "突破K线质量×40% + 当前介入点评分×60%",
        "formula_version": "input_output_pattern_v1",
    }


def combine_technical_scores(
    trend_score: float | None, pattern_score: float | None
) -> dict[str, Any]:
    """Combine a 100-point trend score and a 10-point morphology score."""

    if trend_score is None or pattern_score is None:
        return {
            "score": None,
            "signal_strength": "insufficient_data",
            "formula": "趋势得分×70% + (形态得分×10)×30%",
        }
    score = round(trend_score * 0.7 + pattern_score * 10 * 0.3, 4)
    strength = (
        "strong"
        if score >= 80
        else "medium" if score >= 60 else "weak" if score >= 40 else "avoid_entry"
    )
    return {
        "score": score,
        "signal_strength": strength,
        "formula": "趋势得分×70% + (形态得分×10)×30%",
        "diagnostic_bucket": {
            "trend": (
                "high"
                if trend_score >= 70
                else "medium" if trend_score >= 40 else "low"
            ),
            "pattern": (
                "high"
                if pattern_score >= 8
                else "medium" if pattern_score >= 5 else "low"
            ),
        },
    }


def _detect_phase(bars: list[dict[str, Any]], ma60: float) -> dict[str, Any]:
    recent = bars[-60:]
    prices = [float(row["adj_close"]) for row in recent]
    low = min(prices)
    high = max(prices)
    latest = prices[-1]
    prior_rally = latest / low - 1
    pullback = high / latest - 1
    ma60_distance = latest / ma60 - 1
    if prior_rally > 0.30 and 0.05 <= pullback <= 0.30 and ma60_distance > 0.15:
        name = "high_consolidation"
    elif prior_rally < 0.20 and abs(ma60_distance) < 0.10:
        name = "one_wave_bottom"
    else:
        name = "unclassified"
    return {
        "name": name,
        "prior_rally_pct": round(prior_rally, 6),
        "pullback_pct": round(pullback, 6),
        "ma60_distance_pct": round(ma60_distance, 6),
    }


def _ma_alignment(ma: dict[int, float], previous_ma60: float) -> tuple[str, int]:
    m5, m10, m20, m60 = ma[5], ma[10], ma[20], ma[60]
    ma60_flat = abs(m60 / previous_ma60 - 1) < 0.01
    if m5 > m10 > m20 > m60:
        return "perfect_bull", 15
    if m5 > m10 > m20 and ma60_flat:
        return "strong_bull", 13
    if m5 > m10 > m60 > m20:
        return "weak_bull", 11
    if m5 > m10 and m20 < m10 and m60 < m10:
        return "early_bull", 9
    if m5 > max(m10, m20, m60):
        return "entangled_bull", 7
    if m5 < m10 < m20 < m60:
        return "perfect_bear", 0
    if m5 < m10 < m60 < m20:
        return "strong_bear", 0
    if m5 < m10 and m20 > m5 and m60 > m5:
        return "early_bear", 1
    if m5 < min(m10, m20, m60):
        return "entangled_bear", 3
    return "fully_entangled", 5


def _price_ma_score(price: float, ma10: float, ma60: float) -> tuple[str, int]:
    distance10 = price / ma10 - 1
    distance60 = price / ma60 - 1
    if price > ma10 > ma60:
        return "above_ma10_and_ma60", 15
    if price > ma10 and distance10 < 0.02:
        return "close_above_ma10", 13
    if price > ma10 and distance10 > 0.10:
        return "far_above_ma10", 10
    if ma10 > price > ma60:
        return (
            ("between_near_ma10", 8)
            if abs(distance10) <= abs(distance60)
            else ("between_near_ma60", 5)
        )
    if price < ma60 and abs(distance60) < 0.02:
        return "close_below_ma60", 3
    if price < ma60 < ma10:
        return "below_ma10_and_ma60", 0
    return "mixed", 5


def _price_volume_score(
    price: float, ma5: float, volume: float, volume_ma5: float
) -> tuple[str, int]:
    above = price >= ma5
    high_volume = volume > volume_ma5
    if above and high_volume:
        return "price_volume_rise", 20
    if not above and not high_volume and abs(price / ma5 - 1) <= 0.03:
        return "low_volume_pullback", 16
    if above and not high_volume:
        return "low_volume_rise", 10
    if not above and high_volume and price / ma5 - 1 > -0.03:
        return "volume_break_below_ma5", 4
    if not above and high_volume:
        return "volume_far_below_ma5", 0
    return "neutral", 8


def _candle_volume_score(
    bar: dict[str, Any], previous: dict[str, Any], volume_ma5: float
) -> tuple[str, int]:
    open_price = float(bar.get("open") or bar["adj_close"])
    close = float(bar["adj_close"])
    high = float(bar.get("high") or close)
    low = float(bar.get("low") or close)
    span = max(high - low, close * 1e-9)
    body_ratio = abs(close - open_price) / span
    volume_ratio = float(bar["volume"]) / volume_ma5 if volume_ma5 else 0.0
    daily_return = close / float(previous["adj_close"]) - 1
    if span / close < 0.002 and daily_return >= 0.095 and volume_ratio < 0.5:
        return "one_price_limit_up", 10
    if span / close < 0.002 and daily_return <= -0.095:
        return "one_price_limit_down", 0
    if close > open_price and body_ratio >= 0.60:
        return (
            ("volume_big_bull", 8)
            if volume_ratio >= 1.5
            else ("low_volume_big_bull", 6)
        )
    if close >= open_price and body_ratio < 0.40 and volume_ratio < 1.0:
        return "low_volume_small_bull_or_doji", 5
    upper_shadow = (high - max(open_price, close)) / span
    if close < open_price and upper_shadow > 0.30 and volume_ratio >= 1.5:
        return "volume_long_upper_shadow", 1
    if close < open_price and body_ratio >= 0.60:
        return (
            ("volume_big_bear", 2)
            if volume_ratio >= 1.5
            else ("low_volume_big_bear", 3)
        )
    return "other", 4


def _detect_range(bars: list[dict[str, Any]]) -> dict[str, Any]:
    for duration in range(60, 9, -1):
        window = bars[-duration:]
        low = min(float(row.get("low") or row["adj_close"]) for row in window)
        high = max(float(row.get("high") or row["adj_close"]) for row in window)
        amplitude = high / low - 1
        prior = bars[-min(len(bars), duration + 60) : -duration]
        prior_low = min(
            (float(row.get("low") or row["adj_close"]) for row in prior), default=low
        )
        prior_rally = high / prior_low - 1
        if amplitude < 0.15 and prior_rally > 0.30:
            return {
                "type": "high_small_consolidation",
                "duration": duration,
                "amplitude_pct": round(amplitude, 6),
                "prior_rally_pct": round(prior_rally, 6),
            }
    window = bars[-120:]
    low = min(float(row.get("low") or row["adj_close"]) for row in window)
    high = max(float(row.get("high") or row["adj_close"]) for row in window)
    amplitude = high / low - 1
    return {
        "type": (
            "large_range" if len(window) > 60 and amplitude > 0.30 else "unclassified"
        ),
        "duration": len(window),
        "amplitude_pct": round(amplitude, 6),
    }


def _find_recent_breakout(
    bars: list[dict[str, Any]], range_duration: int
) -> tuple[int, float] | None:
    lookback = min(max(range_duration, 10), 60)
    for index in range(len(bars) - 1, max(lookback, len(bars) - 21) - 1, -1):
        prior = bars[index - lookback : index]
        if not prior:
            continue
        upper = max(float(row.get("high") or row["adj_close"]) for row in prior)
        close = float(bars[index]["adj_close"])
        previous_close = float(bars[index - 1]["adj_close"])
        if close > upper and close / previous_close - 1 > 0.05:
            return index, upper
    return None


def _breakout_quality(bars: list[dict[str, Any]], index: int) -> dict[str, Any]:
    bar = bars[index]
    previous = bars[index - 1]
    open_price = float(bar.get("open") or bar["adj_close"])
    close = float(bar["adj_close"])
    high = float(bar.get("high") or close)
    low = float(bar.get("low") or close)
    span = max(high - low, close * 1e-9)
    body_ratio = (close - open_price) / span
    rise = close / float(previous["adj_close"]) - 1
    baseline = mean(float(row["volume"]) for row in bars[max(0, index - 5) : index])
    volume_ratio = float(bar["volume"]) / baseline if baseline else 0.0
    upper_shadow = (high - close) / span
    body_score = 4 if body_ratio > 0.70 else 2 if body_ratio >= 0.50 else 0
    rise_score = 3 if rise > 0.07 else 2 if rise >= 0.05 else 1 if rise >= 0.03 else 0
    volume_score = 2 if volume_ratio > 2 else 1 if volume_ratio >= 1.5 else 0
    shadow_score = 1 if upper_shadow < 0.10 else 0.5 if upper_shadow <= 0.30 else 0
    return {
        "score": body_score + rise_score + volume_score + shadow_score,
        "body_ratio": round(body_ratio, 6),
        "daily_return": round(rise, 6),
        "volume_ratio": round(volume_ratio, 4),
        "upper_shadow_ratio": round(upper_shadow, 6),
    }


def _entry_score(
    bars: list[dict[str, Any]], breakout_index: int, upper: float
) -> dict[str, Any]:
    latest = float(bars[-1]["adj_close"])
    breakout_close = float(bars[breakout_index]["adj_close"])
    days = len(bars) - 1 - breakout_index
    distance = abs(latest / upper - 1)
    if days <= 1 and latest >= breakout_close:
        location = (
            10
            if distance < 0.03
            else (
                7
                if distance <= 0.05
                else 4 if distance <= 0.08 else 2 if distance <= 0.12 else 0
            )
        )
        state = 10 if days == 0 else 6
        entry_type = "first_breakout_entry"
    else:
        pullback = (breakout_close - latest) / max(
            breakout_close - upper, breakout_close * 1e-9
        )
        location = (
            10
            if distance < 0.03
            else (
                7
                if latest >= (breakout_close + upper) / 2
                else 5 if latest >= upper else 2 if pullback <= 0.80 else 0
            )
        )
        latest_bar = bars[-1]
        open_price = float(latest_bar.get("open") or latest)
        high = float(latest_bar.get("high") or latest)
        low = float(latest_bar.get("low") or latest)
        body_ratio = abs(latest - open_price) / max(high - low, latest * 1e-9)
        volume_baseline = mean(float(row["volume"]) for row in bars[-6:-1])
        volume_contracting = (
            float(latest_bar["volume"]) < volume_baseline if volume_baseline else False
        )
        state = (
            10
            if latest < open_price and body_ratio < 0.40 and volume_contracting
            else 6 if body_ratio < 0.40 else 0
        )
        entry_type = "second_pullback_entry"
    return {
        "type": entry_type,
        "days_since_breakout": days,
        "location_score": location,
        "state_score": state,
        "score": round(location * 0.5 + state * 0.5, 4),
    }


def _trailing_mean(values: list[float], window: int) -> float:
    return mean(values[-window:])
