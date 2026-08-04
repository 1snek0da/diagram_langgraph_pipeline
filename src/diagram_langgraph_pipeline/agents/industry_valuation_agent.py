"""Industry value scenarios derived from communication-capex forecasts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "industry_valuation", state)
    forecast = state.get("future_capex_forecast_result", {})
    current_market_cap = _decimal(payload.get("current_market_cap"))
    fx_rate = _decimal(payload.get("fx_rate_usd_cny"))
    share_low = Decimal(str(payload.get("addressable_share_low", "0.35")))
    share_high = Decimal(str(payload.get("addressable_share_high", "0.40")))
    net_margin = Decimal(str(payload.get("net_margin", "0.30")))
    pe_low = Decimal(str(payload.get("pe_low", "30")))
    pe_high = Decimal(str(payload.get("pe_high", "35")))
    scenarios: list[dict[str, Any]] = []
    missing: list[str] = list(forecast.get("missing_items", []))

    for item in forecast.get("forecasts", []):
        capex = _decimal(item.get("communication_capex"))
        currency = str(item.get("currency") or "CNY").upper()
        if capex is None:
            continue
        if currency == "USD":
            if fx_rate is None:
                if "缺少USD/CNY汇率" not in missing:
                    missing.append("缺少USD/CNY汇率")
                continue
            capex_cny = capex * fx_rate
        elif currency == "CNY":
            capex_cny = capex
        else:
            missing.append(f"暂不支持{currency}转换为CNY")
            continue
        revenue_low = capex_cny * share_low
        revenue_high = capex_cny * share_high
        profit_low = revenue_low * net_margin
        profit_high = revenue_high * net_margin
        market_cap_low = profit_low * pe_low
        market_cap_high = profit_high * pe_high
        scenarios.append(
            {
                "scenario_name": item.get("scenario_name"),
                "forecast_year": item.get("forecast_year"),
                "communication_capex_original": capex,
                "original_currency": currency,
                "fx_rate_usd_cny": fx_rate if currency == "USD" else Decimal("1"),
                "fx_rate_date": payload.get("fx_rate_date"),
                "communication_capex_cny": capex_cny,
                "addressable_revenue_low": revenue_low,
                "addressable_revenue_high": revenue_high,
                "estimated_profit_low": profit_low,
                "estimated_profit_high": profit_high,
                "reasonable_market_cap_low": market_cap_low,
                "reasonable_market_cap_high": market_cap_high,
                "upside_low": market_cap_low / current_market_cap - Decimal("1") if current_market_cap else None,
                "upside_high": market_cap_high / current_market_cap - Decimal("1") if current_market_cap else None,
            }
        )

    if not scenarios and payload.get("scenarios"):
        scenarios = _legacy_scenarios(payload.get("scenarios", []), current_market_cap)

    confidence = payload.get("confidence_score")
    if confidence is None:
        confidence = min(Decimal("0.85"), Decimal(str(forecast.get("confidence_score", "0.1"))))
        if not current_market_cap:
            confidence = min(confidence, Decimal("0.35"))
    evidence = evidence_from(payload, "industry_valuation")
    evidence_ids = [item.get("evidence_id") for item in evidence if item.get("evidence_id")]
    assumptions = [
        {
            "name": "a_share_addressable_share",
            "low": share_low,
            "high": share_high,
            "basis": "user_document_assumption",
            "source_reference": "行业分析.docx:行业未来价值测算",
            "evidence_ids": evidence_ids,
        },
        {
            "name": "net_margin",
            "value": net_margin,
            "basis": "user_document_assumption",
            "source_reference": "行业分析.docx:行业未来价值测算",
            "evidence_ids": evidence_ids,
        },
        {
            "name": "pe_range",
            "low": pe_low,
            "high": pe_high,
            "basis": "user_document_assumption",
            "source_reference": "行业分析.docx:行业未来价值测算",
            "evidence_ids": evidence_ids,
        },
        *payload.get("assumptions", []),
    ]
    return {
        "industry_valuation_result": {
            "current_market_cap": current_market_cap,
            "current_market_cap_currency": payload.get("current_market_cap_currency", "CNY"),
            "universe_id": payload.get("universe_id"),
            "universe_as_of_date": payload.get("universe_as_of_date"),
            "scenarios": scenarios,
            "assumptions": assumptions,
            "confidence_score": confidence,
            "formula_version": "industry_capex_pe_v1",
            "missing_items": list(dict.fromkeys(missing)),
            "evidence": evidence,
        }
    }


def _legacy_scenarios(items: list[dict[str, Any]], current_market_cap: Decimal | None) -> list[dict[str, Any]]:
    result = []
    for item in items:
        profit = _decimal(item.get("future_profit"))
        revenue = _decimal(item.get("future_revenue"))
        pe = _decimal(item.get("assumed_pe"))
        ps = _decimal(item.get("assumed_ps"))
        estimated = profit * pe if profit is not None and pe is not None else (
            revenue * ps if revenue is not None and ps is not None else None
        )
        result.append(
            {
                **item,
                "estimated_market_cap": estimated,
                "upside_pct": estimated / current_market_cap - Decimal("1") if estimated and current_market_cap else None,
                "legacy_compatibility": True,
            }
        )
    return result


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
