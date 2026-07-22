"""Pure-Python market metrics with explicit missing-data handling."""

from __future__ import annotations

from math import log, sqrt
from statistics import mean, pstdev
from typing import Any, Iterable


RETURN_WINDOWS = (5, 20, 60, 120, 250)
MA_WINDOWS = (20, 60, 120, 250)


def analyze_market_payload(
    payload: dict[str, Any],
    benchmark_payload: dict[str, Any] | None = None,
    sector_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bars = normalize_bars(payload.get("bars", []))
    valuations = normalize_valuations(payload.get("valuations", []))
    closes = [_price(bar) for bar in bars]

    returns = {f"return_{window}d": _period_return(closes, window) for window in RETURN_WINDOWS}
    ma_status = {f"ma{window}": _ma_position(closes, window) for window in MA_WINDOWS}
    volatility_20d = _annualized_volatility(closes[-21:])
    max_drawdown = _max_drawdown(closes)
    atr14 = _atr(bars, 14)
    volume_price = _volume_price_signal(bars)
    valuation_percentiles = _valuation_percentiles(valuations)
    abnormal_events = _abnormal_events(bars)
    relative_strength = {
        "vs_benchmark": _relative_returns(closes, benchmark_payload),
        "vs_sector": _relative_returns(closes, sector_payload),
    }

    expected_days = 251
    coverage_ratio = min(len(bars) / expected_days, 1.0)
    missing: list[str] = []
    if len(bars) < 21:
        missing.append("至少需要 21 个交易日计算短期趋势与波动")
    if len(bars) < 251:
        missing.append("不足 251 个交易日，250 日收益或均线可能缺失")
    if len(valuations) < 20:
        missing.append("估值历史样本不足 20 条，历史分位可信度较低")
    if benchmark_payload is None:
        missing.append("缺少大盘指数行情，无法计算大盘超额收益")
    if sector_payload is None:
        missing.append("缺少行业指数行情，无法计算行业超额收益")

    return {
        **returns,
        "volatility_20d": volatility_20d,
        "max_drawdown": max_drawdown,
        "atr14": atr14,
        "ma_status": ma_status,
        "volume_price_signal": volume_price,
        "valuation_percentile": valuation_percentiles,
        "relative_strength": relative_strength,
        "abnormal_events": abnormal_events,
        "latest_close": closes[-1] if closes else None,
        "data_coverage": {
            "bar_count": len(bars),
            "valuation_count": len(valuations),
            "coverage_ratio": round(coverage_ratio, 4),
            "source": payload.get("source", "unknown"),
            "missing_items": missing,
        },
    }


def normalize_bars(raw_bars: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw_bars:
        close = _to_float(item.get("adj_close", item.get("close")))
        if close is None or close <= 0:
            continue
        rows.append(
            {
                "trade_date": str(item.get("trade_date", item.get("date", ""))),
                "open": _to_float(item.get("open")),
                "high": _to_float(item.get("high")),
                "low": _to_float(item.get("low")),
                "close": _to_float(item.get("close")) or close,
                "adj_close": close,
                "volume": _to_float(item.get("volume")) or 0.0,
                "turnover_amount": _to_float(item.get("turnover_amount")),
                "turnover_rate": _to_float(item.get("turnover_rate")),
            }
        )
    return sorted(rows, key=lambda row: row["trade_date"])


def normalize_valuations(raw_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in raw_rows]
    return sorted(rows, key=lambda row: str(row.get("trade_date", "")))


def _price(bar: dict[str, Any]) -> float:
    return float(bar["adj_close"])


def _period_return(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    return round(closes[-1] / closes[-window - 1] - 1, 6)


def _ma_position(closes: list[float], window: int) -> dict[str, Any]:
    if len(closes) < window:
        return {"value": None, "price_position": "insufficient_data", "distance_pct": None}
    value = mean(closes[-window:])
    distance = closes[-1] / value - 1
    return {
        "value": round(value, 4),
        "price_position": "above" if distance >= 0 else "below",
        "distance_pct": round(distance, 6),
    }


def _annualized_volatility(closes: list[float]) -> float | None:
    if len(closes) < 3:
        return None
    log_returns = [log(current / previous) for previous, current in zip(closes, closes[1:])]
    return round(pstdev(log_returns) * sqrt(252), 6)


def _max_drawdown(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak = closes[0]
    worst = 0.0
    for close in closes:
        peak = max(peak, close)
        worst = min(worst, close / peak - 1)
    return round(worst, 6)


def _atr(bars: list[dict[str, Any]], window: int) -> dict[str, float | None]:
    if len(bars) < window + 1:
        return {"value": None, "percent": None}
    true_ranges: list[float] = []
    for previous, current in zip(bars[-window - 1 : -1], bars[-window:]):
        high = current.get("high")
        low = current.get("low")
        if high is None or low is None:
            continue
        previous_close = _price(previous)
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    if not true_ranges:
        return {"value": None, "percent": None}
    value = mean(true_ranges)
    return {"value": round(value, 4), "percent": round(value / _price(bars[-1]), 6)}


def _volume_price_signal(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if len(bars) < 25:
        return {"signal": "insufficient_data", "volume_ratio": None, "return_5d": None}
    recent_volume = mean(float(row["volume"]) for row in bars[-5:])
    baseline_volume = mean(float(row["volume"]) for row in bars[-25:-5])
    ratio = recent_volume / baseline_volume if baseline_volume else None
    return_5d = _period_return([_price(row) for row in bars], 5)
    if ratio is None or return_5d is None:
        signal = "insufficient_data"
    elif ratio >= 1.3 and return_5d > 0.02:
        signal = "放量上涨"
    elif ratio >= 1.3 and return_5d < -0.02:
        signal = "放量下跌"
    elif ratio < 0.8 and return_5d > 0:
        signal = "缩量反弹"
    elif ratio < 0.8:
        signal = "成交萎缩"
    else:
        signal = "量价中性"
    return {
        "signal": signal,
        "volume_ratio": round(ratio, 4) if ratio is not None else None,
        "return_5d": return_5d,
    }


def _valuation_percentiles(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("pe_ttm", "pb", "ps_ttm"):
        values = [_to_float(row.get(key)) for row in rows]
        valid = [value for value in values if value is not None and value > 0]
        current = next((value for value in reversed(values) if value is not None and value > 0), None)
        percentile = None
        if current is not None and len(valid) >= 2:
            percentile = sum(value <= current for value in valid) / len(valid)
        result[key] = {
            "current": current,
            "percentile": round(percentile, 4) if percentile is not None else None,
            "sample_size": len(valid),
        }
    return result


def _abnormal_events(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if len(bars) < 2:
        return events
    baseline_volumes = [float(row["volume"]) for row in bars[-61:-1] if row.get("volume")]
    baseline = mean(baseline_volumes) if baseline_volumes else 0.0
    for previous, current in zip(bars[-21:-1], bars[-20:]):
        previous_close = _price(previous)
        close = _price(current)
        daily_return = close / previous_close - 1
        open_price = current.get("open")
        gap = open_price / previous_close - 1 if open_price else 0.0
        volume_ratio = float(current["volume"]) / baseline if baseline else 0.0
        if abs(gap) >= 0.03:
            events.append({"date": current["trade_date"], "type": "gap", "value": round(gap, 6)})
        if abs(daily_return) >= 0.07:
            events.append(
                {"date": current["trade_date"], "type": "large_daily_move", "value": round(daily_return, 6)}
            )
        if volume_ratio >= 2.5:
            events.append(
                {"date": current["trade_date"], "type": "abnormal_volume", "value": round(volume_ratio, 4)}
            )
    for window in MA_WINDOWS:
        if len(bars) < window + 1:
            continue
        closes = [_price(row) for row in bars]
        previous_ma = mean(closes[-window - 1 : -1])
        current_ma = mean(closes[-window:])
        if closes[-2] <= previous_ma < closes[-1]:
            events.append({"date": bars[-1]["trade_date"], "type": f"break_above_ma{window}"})
        elif closes[-2] >= previous_ma > closes[-1]:
            events.append({"date": bars[-1]["trade_date"], "type": f"break_below_ma{window}"})
    return events


def _relative_returns(closes: list[float], payload: dict[str, Any] | None) -> dict[str, float | None]:
    if not payload:
        return {f"excess_return_{window}d": None for window in (20, 60, 120, 250)}
    benchmark = [_price(row) for row in normalize_bars(payload.get("bars", []))]
    result: dict[str, float | None] = {}
    for window in (20, 60, 120, 250):
        stock_return = _period_return(closes, window)
        benchmark_return = _period_return(benchmark, window)
        value = None if stock_return is None or benchmark_return is None else stock_return - benchmark_return
        result[f"excess_return_{window}d"] = round(value, 6) if value is not None else None
    return result


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None
