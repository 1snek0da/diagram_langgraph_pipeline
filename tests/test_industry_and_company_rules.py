from decimal import Decimal

from diagram_langgraph_pipeline.agents import (
    business_agent,
    future_capex_forecast_agent,
    industry_valuation_agent,
    marginal_change_agent,
    policy_agent,
    profit_forecast_agent,
    upstream_capex_agent,
)
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}))


def _state(research_inputs):
    return {
        "run_id": "rules",
        "ticker": "TEST",
        "company_name": "测试公司",
        "industry_name": "光通信",
        "as_of_date": "2026-07-21",
        "research_inputs": research_inputs,
    }


def test_nvidia_is_supply_only_and_not_in_demand_total():
    state = _state(
        {
            "upstream_capex": {
                "records": [
                    {
                        "company_name": "Alphabet",
                        "entity_id": "alphabet",
                        "fiscal_year": 2025,
                        "total_capex": 100,
                        "communication_capex": 20,
                    },
                    {
                        "company_name": "NVIDIA",
                        "entity_id": "nvidia",
                        "fiscal_year": 2025,
                        "total_capex": 999,
                        "communication_capex": 999,
                    },
                ]
            }
        }
    )

    result = upstream_capex_agent.run(state, DEPS)["upstream_capex_result"]

    assert result["demand_side"]["annual_aggregate"][0]["total_capex"] == Decimal("100")
    assert result["supply_side"]["records"][0]["entity_id"] == "nvidia"
    assert result["supply_side"]["included_in_demand_total"] is False


def test_missing_communication_capex_stays_null_and_blocks_forecast():
    state = _state(
        {
            "upstream_capex": {
                "records": [
                    {
                        "company_name": "Alphabet",
                        "entity_id": "alphabet",
                        "fiscal_year": year,
                        "total_capex": amount,
                    }
                    for year, amount in ((2023, 100), (2024, 120), (2025, 150))
                ]
            }
        }
    )
    upstream = upstream_capex_agent.run(state, DEPS)["upstream_capex_result"]
    forecast = future_capex_forecast_agent.run(
        {**state, "upstream_capex_result": upstream, "policy_result": {"direction": "neutral"}},
        DEPS,
    )["future_capex_forecast_result"]

    assert all(item["communication_capex"] is None for item in upstream["demand_side"]["records"])
    assert "缺少可核验的通信相关CapEx" in upstream["missing_items"]
    assert forecast["forecasts"] == []


def test_forecast_requires_three_years_and_nonquantified_policy_does_not_change_formula():
    short = {
        "upstream_capex_result": {
            "demand_side": {
                "annual_aggregate": [
                    {"fiscal_year": 2024, "communication_capex": Decimal("10"), "currency": "USD"},
                    {"fiscal_year": 2025, "communication_capex": Decimal("12"), "currency": "USD"},
                ]
            },
            "company_coverage": {"coverage_ratio": Decimal("1")},
        },
        "policy_result": {"direction": "positive", "quantified_impact_pct": None},
    }
    assert future_capex_forecast_agent.run(short, DEPS)["future_capex_forecast_result"]["forecasts"] == []

    complete = {
        **short,
        "upstream_capex_result": {
            "demand_side": {
                "annual_aggregate": [
                    {"fiscal_year": 2022, "communication_capex": Decimal("10"), "currency": "USD"},
                    {"fiscal_year": 2023, "communication_capex": Decimal("11"), "currency": "USD"},
                    {"fiscal_year": 2024, "communication_capex": Decimal("13.2"), "currency": "USD"},
                    {"fiscal_year": 2025, "communication_capex": Decimal("15.84"), "currency": "USD"},
                ]
            },
            "company_coverage": {"coverage_ratio": Decimal("1")},
        },
    }
    forecast = future_capex_forecast_agent.run(complete, DEPS)["future_capex_forecast_result"]

    assert len(forecast["forecasts"]) == 6
    assert forecast["forecast_method"] == "historical_quantile"
    assert any("不进入预测公式" in item for item in forecast["warnings"])


def test_legacy_industry_trend_is_read_only_as_non_numeric_compatibility_input():
    state = {
        "industry_trend_result": {"trend": "positive"},
        "upstream_capex_result": {"demand_side": {"annual_aggregate": []}},
        "policy_result": {"direction": "neutral"},
    }

    result = future_capex_forecast_agent.run(state, DEPS)["future_capex_forecast_result"]

    assert result["trend"] == "positive"
    assert result["forecasts"] == []
    assert result["forecast_method"] == "legacy_trend_compatibility_no_numeric_forecast"


def test_sourced_consensus_is_used_when_history_is_insufficient_without_fabricating_scenarios():
    state = {
        "as_of_date": "2026-07-21",
        "upstream_capex_result": {
            "demand_side": {"annual_aggregate": []},
            "company_coverage": {"coverage_ratio": Decimal("0.4")},
            "consensus_forecasts": [
                {
                    "forecast_year": 2027,
                    "scenario_name": "base",
                    "communication_capex": Decimal("100"),
                    "currency": "USD",
                    "published_at": "2026-07-01T00:00:00+08:00",
                    "institution": "licensed consensus",
                    "source_id": "report:1",
                },
                {
                    "forecast_year": 2028,
                    "scenario_name": "base",
                    "communication_capex": Decimal("110"),
                    "currency": "USD",
                    "published_at": "2026-07-01T00:00:00+08:00",
                    "institution": "licensed consensus",
                    "source_id": "report:1",
                },
            ],
        },
        "policy_result": {"direction": "neutral"},
    }

    result = future_capex_forecast_agent.run(state, DEPS)["future_capex_forecast_result"]

    assert result["forecast_method"] == "sourced_consensus"
    assert len(result["forecasts"]) == 2
    assert "一致预期缺少bear场景" in result["missing_items"]


def test_industry_formula_and_leader_premium_are_decimal_reproducible():
    state = _state(
        {
            "industry_valuation": {
                "current_market_cap": "1000",
                "fx_rate_usd_cny": "7",
                "fx_rate_date": "2026-07-20",
            },
            "business": {
                "business_summary": "公司专注光模块",
                "company_type": "optical_module",
                "market_share_rank": 1,
            },
        }
    )
    state["future_capex_forecast_result"] = {
        "forecasts": [
            {
                "scenario_name": "base",
                "forecast_year": 2027,
                "communication_capex": Decimal("100"),
                "currency": "USD",
            }
        ],
        "confidence_score": Decimal("0.8"),
        "missing_items": [],
    }

    industry = industry_valuation_agent.run(state, DEPS)["industry_valuation_result"]["scenarios"][0]
    business = business_agent.run(state, DEPS)["business_result"]

    assert industry["reasonable_market_cap_low"] == Decimal("2205.00")
    assert industry["reasonable_market_cap_high"] == Decimal("2940.00")
    assert business["final_pe_range"] == {"low": Decimal("27.50"), "high": Decimal("42.00")}


def test_market_position_adjustments_follow_document_ranges():
    rank_four = _state(
        {
            "business": {
                "business_summary": "光芯片公司",
                "company_type": "optical_chip",
                "market_share_rank": 4,
            }
        }
    )
    rank_six = _state(
        {
            "business": {
                "business_summary": "通信设备公司",
                "company_type": "communication_equipment",
                "market_share_rank": 6,
            }
        }
    )

    second_tier = business_agent.run(rank_four, DEPS)["business_result"]
    lower_tier = business_agent.run(rank_six, DEPS)["business_result"]

    assert second_tier["final_pe_range"] == {"low": Decimal("60"), "high": Decimal("80")}
    assert lower_tier["final_pe_range"] == {"low": Decimal("12.00"), "high": Decimal("22.50")}


def test_profit_and_events_after_as_of_are_excluded():
    state = _state(
        {
            "profit_forecast": {
                "forecasts": [
                    {
                        "forecast_year": 2027,
                        "published_at": "2026-07-20T00:00:00+08:00",
                        "net_profit_forecast": 10,
                    },
                    {
                        "forecast_year": 2027,
                        "published_at": "2026-07-22T00:00:00+08:00",
                        "net_profit_forecast": 99,
                    },
                ]
            },
            "marginal_change": {
                "events": [
                    {
                        "event_type": "order",
                        "event_summary": "历史订单",
                        "published_at": "2026-07-20T00:00:00+08:00",
                    },
                    {
                        "event_type": "order",
                        "event_summary": "未来订单",
                        "published_at": "2026-07-22T00:00:00+08:00",
                    },
                ]
            },
        }
    )

    forecasts = profit_forecast_agent.run(state, DEPS)["profit_forecast_result"]
    events = marginal_change_agent.run(state, DEPS)["marginal_change_result"]

    assert len(forecasts["forecasts"]) == 1
    assert forecasts["excluded_forecasts"][0]["reason"] == "after_as_of_date"
    assert len(events["events"]) == 1
    assert events["excluded_events"][0]["reason"] == "after_as_of_date"


def test_policy_numeric_adjustment_requires_source_evidence():
    unsupported = _state(
        {
            "policy": {
                "summary": "无来源量化值",
                "direction": "positive",
                "quantified_impact_pct": "0.10",
            }
        }
    )
    supported = _state(
        {
            "policy": {
                "summary": "有来源量化值",
                "direction": "positive",
                "quantified_impact_pct": "0.10",
                "evidence": [{"claim_text": "政策原文明确量化影响"}],
            }
        }
    )

    unsupported_result = policy_agent.run(unsupported, DEPS)["policy_result"]
    supported_result = policy_agent.run(supported, DEPS)["policy_result"]

    assert unsupported_result["quantified_impact_pct"] is None
    assert supported_result["quantified_impact_pct"] == Decimal("0.10")
