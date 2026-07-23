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
    forecasts = state.get("profit_forecast_result", {}).get("forecasts", [])
    current_market_cap = _decimal(payload.get("current_market_cap"))
    if current_market_cap is None:
        valuations = state.get("stock_market_data", {}).get("stock", {}).get("valuations", [])
        if valuations:
            current_market_cap = _decimal(valuations[-1].get("market_cap"))

    target_year = max((item.get("forecast_year", 0) for item in forecasts), default=None)
    target_forecasts = [item for item in forecasts if item.get("forecast_year") == target_year]
    forecast_values = [
        value
        for value in (_decimal(item.get("net_profit_forecast")) for item in target_forecasts)
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
        base_pe = _decimal(payload.get("base_pe")) or _decimal(target_forecast.get("pe_assumption"))
        pe_low = pe_high = base_pe
        pe_basis = "explicit_or_forecast_pe"

    scenarios: list[dict[str, Any]] = []
    valuation_range = None
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
                    "upside_pct": estimated / current_market_cap - Decimal("1") if current_market_cap else None,
                }
            )
        valuation_range = {
            "low": scenarios[0]["estimated_market_cap"],
            "high": scenarios[-1]["estimated_market_cap"],
            "upside_low": scenarios[0]["upside_pct"],
            "upside_high": scenarios[-1]["upside_pct"],
        }

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
            "current_market_cap_currency": payload.get("current_market_cap_currency", "CNY"),
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
            "final_pe_range": {"low": pe_low, "high": pe_high} if pe_low is not None and pe_high is not None else None,
            "pe_basis": pe_basis,
            "formula_version": "company_pe_v1",
            "scenarios": scenarios,
            "valuation_range": valuation_range,
            "valuation_percentile": state.get("stock_market_data_analysis", {}).get("valuation_percentile", {}),
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


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None
