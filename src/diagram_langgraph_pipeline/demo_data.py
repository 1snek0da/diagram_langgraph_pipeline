"""Offline demo fixtures used by the CLI and tests."""

from __future__ import annotations

from datetime import date, timedelta
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
    evidence = lambda claim: [{"claim_text": claim, "source": "demo", "confidence_score": 0.8}]
    return {
        "industry_report": {
            "summary": "行业需求保持增长，技术路线仍在迭代。",
            "market_size": 5000,
            "technology_routes": ["路线 A", "路线 B"],
            "evidence": evidence("示例行业报告显示需求增长"),
        },
        "upstream_capex": {
            "records": [{"company_name": "上游公司", "capex_change_pct": 0.18}],
            "demand_signal": "上游扩产支持中期需求",
            "evidence": evidence("上游资本开支同比增长 18%"),
        },
        "policy": {
            "direction": "supportive",
            "impact_horizon": "medium",
            "summary": "政策环境偏支持。",
            "evidence": evidence("示例政策文件支持产业升级"),
        },
        "industry_valuation": {
            "current_market_cap": 3500,
            "scenarios": [{"scenario_name": "base", "future_profit": 240, "assumed_pe": 20}],
        },
        "business": {
            "business_summary": "公司主营与行业高景气环节直接相关。",
            "industry_linkage": "strong",
            "growth_drivers": ["产能释放", "产品升级"],
            "risks": ["需求不及预期"],
            "evidence": evidence("主营收入主要来自目标行业"),
        },
        "profit_forecast": {
            "revision_direction": "up",
            "forecasts": [{"forecast_year": 2027, "net_profit_forecast": 18, "eps_forecast": 1.8, "pe_assumption": 25}],
            "evidence": evidence("一致预期净利润上修"),
        },
        "marginal_change": {
            "events": [{"event_type": "capacity_release", "impact_direction": "positive", "event_summary": "新产能投产"}],
            "evidence": evidence("新产线进入量产阶段"),
        },
        "company_valuation": {"forecast_profit": 18, "base_pe": 25},
        "sentiment": {"sentiment_score": 0.35, "heat_score": 0.45, "evidence": evidence("新闻情绪温和偏正面")},
    }
