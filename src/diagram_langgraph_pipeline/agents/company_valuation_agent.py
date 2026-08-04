"""Company valuation using typed company category and position ranges."""

from __future__ import annotations

from decimal import Decimal
from statistics import median
from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "company_valuation", state)
    business = state.get("business_result", {})
    profit_result = state.get("profit_forecast_result", {})
    forecasts = profit_result.get("forecasts", [])
    adjusted_forecasts = profit_result.get("adjusted_forecasts", [])
    current_market_cap = _decimal(payload.get("current_market_cap"))
    if current_market_cap is None:
        valuations = (
            state.get("stock_market_data", {}).get("stock", {}).get("valuations", [])
        )
        if valuations:
            current_market_cap = _decimal(valuations[-1].get("market_cap"))

    valuation_forecasts = adjusted_forecasts or forecasts
    target_year = max(
        (item.get("forecast_year", 0) for item in valuation_forecasts), default=None
    )
    target_forecasts = [
        item for item in valuation_forecasts if item.get("forecast_year") == target_year
    ]
    forecast_values = [
        value
        for value in (
            _decimal(
                item.get("adjusted_net_profit_mid", item.get("net_profit_forecast"))
            )
            for item in target_forecasts
        )
        if value is not None
    ]
    forecast_profit = _decimal(payload.get("forecast_profit"))
    if forecast_profit is None and forecast_values:
        forecast_profit = Decimal(str(median(forecast_values)))
    target_forecast = target_forecasts[-1] if target_forecasts else {}
    pe_range = business.get("final_pe_range")
    if pe_range:
        pe_low = _decimal(pe_range.get("low"))
        pe_high = _decimal(pe_range.get("high"))
        pe_basis = "company_type_and_market_position"
    else:
        base_pe = _decimal(payload.get("base_pe")) or _decimal(
            target_forecast.get("pe_assumption")
        )
        pe_low = pe_high = base_pe
        pe_basis = "explicit_or_forecast_pe"

    scenarios: list[dict[str, Any]] = []
    valuation_range = None
    annual_valuations: list[dict[str, Any]] = []
    investment_signal = {
        "signal": "insufficient_data",
        "basis": "缺少逐年盈利、PE或当前市值",
    }
    if forecast_profit is not None and pe_low is not None and pe_high is not None:
        pe_mid = (pe_low + pe_high) / Decimal("2")
        for name, assumed_pe in (("bear", pe_low), ("base", pe_mid), ("bull", pe_high)):
            estimated = forecast_profit * assumed_pe
            scenarios.append(
                {
                    "scenario_name": name,
                    "forecast_profit": forecast_profit,
                    "assumed_pe": assumed_pe,
                    "estimated_market_cap": estimated,
                    "upside_pct": (
                        estimated / current_market_cap - Decimal("1")
                        if current_market_cap
                        else None
                    ),
                }
            )
        valuation_range = {
            "low": scenarios[0]["estimated_market_cap"],
            "high": scenarios[-1]["estimated_market_cap"],
            "upside_low": scenarios[0]["upside_pct"],
            "upside_high": scenarios[-1]["upside_pct"],
        }
        annual_valuations = _build_annual_valuations(
            valuation_forecasts,
            pe_low,
            pe_high,
            current_market_cap,
        )
        investment_signal = _investment_signal(annual_valuations)

    missing = []
    if forecast_profit is None:
        missing.append("缺少可用预测净利润")
    if pe_low is None or pe_high is None:
        missing.append("缺少公司类型PE区间或明确PE假设")
    if current_market_cap is None:
        missing.append("缺少当前市值")
    confidence = payload.get("confidence_score")
    if confidence is None:
        confidence = Decimal("0.65") if scenarios and not missing else Decimal("0.10")
    return {
        "company_valuation_result": {
            "current_market_cap": current_market_cap,
            "current_market_cap_currency": payload.get(
                "current_market_cap_currency", "CNY"
            ),
            "forecast_profit": forecast_profit,
            "forecast_profit_currency": payload.get("forecast_profit_currency", "CNY"),
            "forecast_year": target_year,
            "forecast_sources": [
                {
                    "institution": item.get("institution"),
                    "published_at": item.get("published_at"),
                    "forecast_basis": item.get("forecast_basis"),
                    "source_id": item.get("source_id"),
                }
                for item in target_forecasts
            ],
            "company_type": business.get("company_type", "unknown"),
            "industry_position": business.get("industry_position", "unknown"),
            "base_pe_range": business.get("base_pe_range"),
            "position_adjustment_range": business.get("position_adjustment_range"),
            "final_pe_range": (
                {"low": pe_low, "high": pe_high}
                if pe_low is not None and pe_high is not None
                else None
            ),
            "pe_basis": pe_basis,
            "formula_version": "company_pe_v2_input_output_doc",
            "scenarios": scenarios,
            "valuation_range": valuation_range,
            "annual_valuations": annual_valuations,
            "investment_signal": investment_signal,
            "valuation_percentile": state.get("stock_market_data_analysis", {}).get(
                "valuation_percentile", {}
            ),
            "assumptions": [
                *payload.get("assumptions", []),
                {
                    "name": "leader_premium",
                    "range": ["1.10", "1.20"],
                    "basis": "user_document_rule",
                    "source_reference": "行业分析.docx:龙头公司溢价",
                },
            ],
            "missing_items": missing,
            "confidence_score": confidence,
            "evidence": evidence_from(payload, "company_valuation"),
        }
    }


def _build_annual_valuations(
    forecasts: list[dict[str, Any]],
    pe_low: Decimal,
    pe_high: Decimal,
    current_market_cap: Decimal | None,
) -> list[dict[str, Any]]:
    by_year: dict[int, list[dict[str, Any]]] = {}
    for item in forecasts:
        year = item.get("forecast_year")
        if isinstance(year, int):
            by_year.setdefault(year, []).append(item)
    rows: list[dict[str, Any]] = []
    pe_mid = (pe_low + pe_high) / Decimal("2")
    for year, items in sorted(by_year.items()):
        profit_lows: list[Decimal] = []
        profit_highs: list[Decimal] = []
        for item in items:
            adjusted_range = item.get("adjusted_net_profit_range") or {}
            low = _decimal(adjusted_range.get("low")) or _decimal(
                item.get("net_profit_forecast")
            )
            high = _decimal(adjusted_range.get("high")) or _decimal(
                item.get("net_profit_forecast")
            )
            if low is not None:
                profit_lows.append(low)
            if high is not None:
                profit_highs.append(high)
        if not profit_lows or not profit_highs:
            continue
        profit_low = Decimal(str(median(profit_lows)))
        profit_high = Decimal(str(median(profit_highs)))
        profit_mid = (profit_low + profit_high) / Decimal("2")
        market_cap_low = profit_low * pe_low
        market_cap_high = profit_high * pe_high
        market_cap_base = profit_mid * pe_mid
        rows.append(
            {
                "forecast_year": year,
                "adjusted_profit_range": {"low": profit_low, "high": profit_high},
                "final_pe_range": {"low": pe_low, "high": pe_high},
                "reasonable_market_cap_range": {
                    "low": market_cap_low,
                    "base": market_cap_base,
                    "high": market_cap_high,
                },
                "upside_range": {
                    "low": (
                        market_cap_low / current_market_cap - Decimal("1")
                        if current_market_cap
                        else None
                    ),
                    "base": (
                        market_cap_base / current_market_cap - Decimal("1")
                        if current_market_cap
                        else None
                    ),
                    "high": (
                        market_cap_high / current_market_cap - Decimal("1")
                        if current_market_cap
                        else None
                    ),
                },
            }
        )
    return rows


def _investment_signal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_year = {item["forecast_year"]: item for item in rows}
    upside_2027 = (by_year.get(2027, {}).get("upside_range") or {}).get("base")
    upside_2028 = (by_year.get(2028, {}).get("upside_range") or {}).get("base")
    if upside_2027 is None and upside_2028 is None:
        return {
            "signal": "insufficient_data",
            "basis": "缺少2027/2028年合理市值空间",
            "upside_2027": upside_2027,
            "upside_2028": upside_2028,
        }
    if upside_2027 is not None and upside_2027 < 0:
        signal = "sell"
        basis = "当前市值高于2027年合理市值基准"
    elif (upside_2027 is not None and upside_2027 >= Decimal("0.50")) or (
        upside_2028 is not None and upside_2028 >= Decimal("1.00")
    ):
        signal = "strong_buy"
        basis = "2027年上行空间不低于50%或2028年不低于100%"
    elif (upside_2027 is not None and upside_2027 >= Decimal("0.30")) or (
        upside_2028 is not None and upside_2028 >= Decimal("0.60")
    ):
        signal = "buy"
        basis = "2027年上行空间不低于30%或2028年不低于60%"
    else:
        signal = "hold"
        basis = "未达到文档定义的买入空间阈值"
    return {
        "signal": signal,
        "basis": basis,
        "upside_2027": upside_2027,
        "upside_2028": upside_2028,
        "valuation_basis": "逐年调整后净利润中值×最终PE中值",
    }


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None
