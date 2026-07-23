"""Offline demo fixtures used by the CLI and tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from math import sin
from typing import Any


def make_market_payload(start_price: float, drift: float, *, days: int = 320) -> dict[str, Any]:
    bars = []
    valuations = []
    current = start_price
    start = date(2025, 1, 1)
    for index in range(days):
        current *= 1 + drift + sin(index / 11) * 0.003
        volume = 1_000_000 * (1 + (index % 7) * 0.04)
        trade_date = (start + timedelta(days=index)).isoformat()
        bars.append(
            {
                "trade_date": trade_date,
                "open": current * 0.995,
                "high": current * 1.012,
                "low": current * 0.988,
                "close": current,
                "adj_close": current,
                "volume": volume,
                "turnover_amount": volume * current,
                "turnover_rate": 0.01 + (index % 5) * 0.001,
            }
        )
        valuations.append(
            {
                "trade_date": trade_date,
                "pe_ttm": 18 + index / days * 5,
                "pb": 2.1 + index / days * 0.5,
                "ps_ttm": 3.0 + index / days * 0.6,
                "market_cap": current * 100_000_000,
            }
        )
    return {"bars": bars, "valuations": valuations, "source": "demo_fixture"}


def demo_research_inputs() -> dict[str, Any]:
    """Return as-of-safe, typed fixtures without needing network credentials."""

    evidence = lambda claim: [{"claim_text": claim, "source": "demo", "confidence_score": 0.8}]
    capex_records: list[dict[str, Any]] = []
    company_values = {
        "alphabet": ("Alphabet", [25, 28, 32, 38]),
        "amazon": ("Amazon", [48, 52, 57, 64]),
        "microsoft": ("Microsoft", [24, 29, 35, 44]),
        "meta": ("Meta", [19, 27, 32, 39]),
        "oracle": ("Oracle", [9, 10, 12, 15]),
    }
    communication_shares = [Decimal("0.22"), Decimal("0.24"), Decimal("0.26"), Decimal("0.29")]
    for entity_id, (company_name, values) in company_values.items():
        for offset, total_capex in enumerate(values):
            capex_records.append(
                {
                    "company_name": company_name,
                    "entity_id": entity_id,
                    "role": "demand",
                    "fiscal_year": 2022 + offset,
                    "total_capex": total_capex,
                    "communication_capex": Decimal(total_capex) * communication_shares[offset],
                    "currency": "USD",
                    "unit": "billion",
                    "scale": 1_000_000_000,
                    "fact_basis": "estimated",
                }
            )
    for offset, total_capex in enumerate([1.0, 1.2, 1.5, 2.1]):
        capex_records.append(
            {
                "company_name": "NVIDIA",
                "entity_id": "nvidia",
                "role": "supply",
                "fiscal_year": 2022 + offset,
                "total_capex": total_capex,
                "currency": "USD",
                "unit": "billion",
                "scale": 1_000_000_000,
                "fact_basis": "reported",
            }
        )

    return {
        "industry_report": {
            "summary": "行业需求保持增长，技术路线仍在迭代。",
            "market_size": 5000,
            "technology_routes": ["路线 A", "路线 B"],
            "evidence": evidence("示例行业报告显示需求增长"),
        },
        "upstream_capex": {
            "records": capex_records,
            "demand_signal": "需求侧扩产支持中期通信需求",
            "evidence": evidence("示例数据按需求侧与供应侧分别列示资本开支"),
        },
        "policy": {
            "direction": "positive",
            "magnitude": "unknown",
            "impact_horizon": "medium",
            "summary": "政策环境偏支持。",
            "events": [
                {
                    "title": "示例产业升级政策",
                    "published_at": "2026-06-01T00:00:00+08:00",
                    "direction": "positive",
                    "magnitude": "unknown",
                    "impact_horizon": "medium",
                    "affected_metrics": ["communication_capex"],
                }
            ],
            "evidence": evidence("示例政策文件支持产业升级"),
        },
        "industry_valuation": {
            "current_market_cap": 3_500_000_000_000,
            "current_market_cap_currency": "CNY",
            "fx_rate_usd_cny": 7.2,
            "fx_rate_date": "2026-07-21",
            "universe_id": "demo-optical-universe-v1",
            "universe_as_of_date": "2026-07-21",
            "evidence": evidence("示例估值参数来自行业分析文档"),
        },
        "business": {
            "business_summary": "公司主营与光模块高景气环节直接相关。",
            "company_type": "optical_module",
            "market_share_rank": 1,
            "revenue_segments": [{"name": "光模块", "revenue_share": 0.82}],
            "industry_linkage": "strong",
            "growth_drivers": ["产能释放", "产品升级"],
            "risks": ["需求不及预期"],
            "evidence": evidence("主营收入主要来自目标行业"),
        },
        "profit_forecast": {
            "revision_direction": "up",
            "forecasts": [
                {
                    "forecast_year": 2027,
                    "institution": "示例券商",
                    "published_at": "2026-07-10T08:00:00+08:00",
                    "forecast_basis": "broker",
                    "revenue_forecast": 48_000_000_000,
                    "net_profit_forecast": 18_000_000_000,
                    "eps_forecast": 1.8,
                    "pe_assumption": 25,
                    "revision_pct": 0.08,
                }
            ],
            "evidence": evidence("示例机构预测净利润上修"),
        },
        "marginal_change": {
            "events": [
                {
                    "event_type": "capacity",
                    "event_date": "2026-07-01",
                    "published_at": "2026-07-02T09:00:00+08:00",
                    "impact_direction": "positive",
                    "certainty": "high",
                    "impact_horizon": "medium",
                    "event_summary": "新产能投产",
                }
            ],
            "evidence": evidence("新产线进入量产阶段"),
        },
        "company_valuation": {
            "current_market_cap": 300_000_000_000,
            "evidence": evidence("当前市值来自示例估值快照"),
        },
        "sentiment": {
            "sentiment_score": 0.35,
            "heat_score": 0.45,
            "evidence": evidence("新闻情绪温和偏正面"),
        },
    }
