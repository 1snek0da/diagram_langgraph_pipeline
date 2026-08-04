"""Transparent two-year communication-capex forecast scenarios."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    upstream = state.get("upstream_capex_result", {})
    policy = state.get("policy_result", {})
    legacy_trend = state.get("industry_trend_result", {})
    history = [
        item
        for item in upstream.get("demand_side", {}).get("annual_aggregate", [])
        if item.get("communication_capex") is not None and item.get("fiscal_year") is not None
    ]
    history.sort(key=lambda item: item["fiscal_year"])
    missing: list[str] = []
    if len(history) < 3:
        missing.append("可比通信CapEx历史少于3个年度")

    growth_rates = [
        current["communication_capex"] / previous["communication_capex"] - Decimal("1")
        for previous, current in zip(history, history[1:])
        if previous["communication_capex"] not in (None, Decimal("0"))
    ]
    recent_growth = growth_rates[-3:]
    forecasts: list[dict[str, Any]] = []
    method = "historical_quantile"
    used_consensus = False
    if len(history) >= 3 and recent_growth:
        base_growth = _quantile(recent_growth, Decimal("0.50"))
        bear_growth = _quantile(growth_rates, Decimal("0.25"))
        bull_growth = _quantile(growth_rates, Decimal("0.75"))
        quantified_policy = policy.get("quantified_impact_pct")
        if quantified_policy is not None:
            adjustment = Decimal(str(quantified_policy))
            base_growth += adjustment
            bear_growth += adjustment
            bull_growth += adjustment
            method = "historical_quantile_plus_quantified_policy"
        last = history[-1]
        as_of = _date_value(state.get("as_of_date")) or date.today()
        forecast_years = [as_of.year + 1, as_of.year + 2]
        for scenario, growth in (("bear", bear_growth), ("base", base_growth), ("bull", bull_growth)):
            for forecast_year in forecast_years:
                year_steps = max(1, forecast_year - int(last["fiscal_year"]))
                amount = Decimal(str(last["communication_capex"])) * (Decimal("1") + growth) ** year_steps
                forecasts.append(
                    {
                        "scenario_name": scenario,
                        "forecast_year": forecast_year,
                        "communication_capex": amount,
                        "currency": last.get("currency"),
                        "growth_rate": growth,
                        "communication_share": last.get("communication_share"),
                        "fact_basis": "derived",
                    }
                )
    else:
        base_growth = bear_growth = bull_growth = None

    if not forecasts:
        as_of = _date_value(state.get("as_of_date")) or date.today()
        sourced_consensus = [
            item
            for item in upstream.get("consensus_forecasts", [])
            if _date_value(item.get("published_at")) is not None
            and _date_value(item.get("published_at")) <= as_of
            and int(item.get("forecast_year", 0)) in {as_of.year + 1, as_of.year + 2}
        ]
        if sourced_consensus:
            missing = [item for item in missing if item != "可比通信CapEx历史少于3个年度"]
            forecasts = [
                {
                    **item,
                    "communication_capex": Decimal(str(item["communication_capex"])),
                    "fact_basis": "estimated",
                }
                for item in sourced_consensus
            ]
            method = "sourced_consensus"
            used_consensus = True
            present_scenarios = {item.get("scenario_name", "base") for item in forecasts}
            for scenario in {"bear", "base", "bull"} - present_scenarios:
                missing.append(f"一致预期缺少{scenario}场景")

    base_growth_value = base_growth if method.startswith("historical") and forecasts else _consensus_growth(forecasts)
    trend = "positive" if base_growth_value is not None and base_growth_value > 0 else (
        "negative" if base_growth_value is not None and base_growth_value < 0 else legacy_trend.get("trend", "neutral")
    )
    coverage = upstream.get("company_coverage", {}).get("coverage_ratio", Decimal("0"))
    confidence = min(
        Decimal("0.90"),
        Decimal("0.20") + Decimal(min(len(history), 5)) * Decimal("0.10") + Decimal(str(coverage)) * Decimal("0.20"),
    ) if forecasts else Decimal("0.10")
    warnings = list(upstream.get("source_warnings", []))
    if used_consensus:
        warnings.append("历史不足，采用带来源且不晚于as_of_date的一致预期")
    if policy.get("direction", "neutral") != "neutral" and policy.get("quantified_impact_pct") is None:
        warnings.append("政策影响缺少量化证据，仅影响风险说明与置信度，不进入预测公式")
    if legacy_trend and not forecasts:
        method = "legacy_trend_compatibility_no_numeric_forecast"
        warnings.append("已读取旧industry_trend_result作为方向提示；无来源数值时仍不生成预测")

    return {
        "future_capex_forecast_result": {
            "trend": trend,
            "forecast_method": method,
            "history": history,
            "history_interval": {
                "start_year": history[0]["fiscal_year"] if history else None,
                "end_year": history[-1]["fiscal_year"] if history else None,
            },
            "growth_history": growth_rates,
            "scenario_growth": {
                "bear": bear_growth if forecasts else None,
                "base": base_growth if forecasts else None,
                "bull": bull_growth if forecasts else None,
            },
            "forecasts": forecasts,
            "policy_assessment": {
                "direction": policy.get("direction", "neutral"),
                "magnitude": policy.get("magnitude", "unknown"),
                "quantified_impact_pct": policy.get("quantified_impact_pct"),
            },
            "confidence_score": confidence,
            "coverage": upstream.get("company_coverage", {}),
            "missing_items": missing,
            "warnings": list(dict.fromkeys(warnings)),
        }
    }


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * Decimal(len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - Decimal(lower_index)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _consensus_growth(forecasts: list[dict[str, Any]]) -> Decimal | None:
    base = sorted(
        [item for item in forecasts if item.get("scenario_name", "base") == "base"],
        key=lambda item: item.get("forecast_year", 0),
    )
    if len(base) < 2:
        return None
    previous = Decimal(str(base[-2]["communication_capex"]))
    current = Decimal(str(base[-1]["communication_capex"]))
    return current / previous - Decimal("1") if previous else None
