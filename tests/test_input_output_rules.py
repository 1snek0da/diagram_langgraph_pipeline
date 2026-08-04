from decimal import Decimal

from diagram_langgraph_pipeline.agents import (
    business_agent,
    company_valuation_agent,
    profit_forecast_agent,
    stock_data_analysis_agent,
    stock_technical_agent,
)
from diagram_langgraph_pipeline.analysis.technical_scoring import (
    combine_technical_scores,
)
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}))


def _flat_then_breakout_bars():
    bars = []
    for index in range(70):
        close = 100 + (index % 5) * 0.1
        bars.append(
            {
                "trade_date": f"2026-01-{index + 1:02d}",
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "adj_close": close,
                "volume": 1_000_000,
            }
        )
    bars[-1].update(
        {
            "open": 101,
            "high": 108,
            "low": 100.5,
            "close": 107,
            "adj_close": 107,
            "volume": 2_200_000,
        }
    )
    return bars


def test_document_technical_scores_are_exposed_by_stock_nodes():
    state = {
        "ticker": "TEST",
        "stock_market_data": {
            "stock": {"bars": _flat_then_breakout_bars(), "valuations": []},
        },
    }
    state.update(stock_data_analysis_agent.run(state, DEPS))
    state.update(stock_technical_agent.run(state, DEPS))

    trend = state["stock_market_data_analysis"]["trend_scoring"]
    technical = state["stock_technical_result"]

    assert state["stock_market_data_analysis"]["ma_status"]["ma5"]["value"] is not None
    assert state["stock_market_data_analysis"]["ma_status"]["ma10"]["value"] is not None
    assert trend["phase"] == "one_wave_bottom"
    assert trend["score"] is not None
    assert technical["pattern_scoring"]["breakout"] is not None
    assert technical["pattern_scoring"]["score"] is not None
    assert technical["composite_scoring"]["score"] is not None


def test_composite_technical_weighting_matches_document():
    result = combine_technical_scores(80, 9)

    assert result["score"] == 83
    assert result["signal_strength"] == "strong"
    assert result["diagnostic_bucket"] == {"trend": "high", "pattern": "high"}


def test_two_stage_profit_revision_and_annual_valuation():
    quarterly = [
        {
            "period": "2025Q1",
            "fiscal_year": 2025,
            "quarter": 1,
            "revenue": 40,
            "net_profit": 12,
            "adjusted_net_profit": 11,
            "gross_margin": "0.38",
            "net_margin": "0.20",
            "inventory": 10,
            "prepayments": 5,
            "contract_liabilities": 8,
            "construction_in_progress": 5,
            "research_expense": 4,
            "fx_loss": 1,
        },
        {
            "period": "2025Q2",
            "fiscal_year": 2025,
            "quarter": 2,
            "revenue": 45,
            "net_profit": 21,
            "adjusted_net_profit": 20,
            "gross_margin": "0.39",
            "net_margin": "0.21",
            "inventory": 11,
            "prepayments": 6,
            "contract_liabilities": 10,
            "construction_in_progress": 6,
            "research_expense": 5,
            "fx_loss": 1,
        },
        {
            "period": "2025Q3",
            "fiscal_year": 2025,
            "quarter": 3,
            "revenue": 50,
            "net_profit": 22,
            "adjusted_net_profit": 21,
            "gross_margin": "0.40",
            "net_margin": "0.22",
            "inventory": 12,
            "prepayments": 7,
            "contract_liabilities": 12,
            "construction_in_progress": 7,
            "research_expense": 6,
            "fx_loss": 1,
        },
        {
            "period": "2025Q4",
            "fiscal_year": 2025,
            "quarter": 4,
            "revenue": 55,
            "net_profit": 24,
            "adjusted_net_profit": 23,
            "gross_margin": "0.41",
            "net_margin": "0.23",
            "inventory": 13,
            "prepayments": 8,
            "contract_liabilities": 14,
            "construction_in_progress": 8,
            "research_expense": 7,
            "fx_loss": 1,
        },
        {
            "period": "2026Q1",
            "fiscal_year": 2026,
            "quarter": 1,
            "revenue": 75,
            "net_profit": 40,
            "adjusted_net_profit": 39,
            "gross_margin": "0.44",
            "net_margin": "0.25",
            "inventory": 18,
            "prepayments": 12,
            "contract_liabilities": 20,
            "construction_in_progress": 7,
            "research_expense": 6,
            "fx_loss": 1,
        },
        {
            "period": "2026Q2",
            "fiscal_year": 2026,
            "quarter": 2,
            "revenue": 85,
            "net_profit": 35,
            "adjusted_net_profit": 34,
            "gross_margin": "0.45",
            "net_margin": "0.26",
            "inventory": 25,
            "prepayments": 17,
            "contract_liabilities": 28,
            "construction_in_progress": 8,
            "research_expense": 7,
            "fx_loss": 1,
        },
    ]
    research_inputs = {
        "business": {
            "business_summary": "光模块龙头",
            "company_type": "optical_module",
            "market_share_rank": 1,
        },
        "profit_forecast": {
            "forecasts": [
                {
                    "forecast_year": year,
                    "institution": "测试券商",
                    "published_at": "2026-07-01T00:00:00+08:00",
                    "forecast_basis": "broker",
                    "net_profit_forecast": profit,
                }
                for year, profit in ((2026, 100), (2027, 120), (2028, 150))
            ],
            "quarterly_financials": quarterly,
            "product_information": {"upgrade_shipment": True},
        },
        "company_valuation": {"current_market_cap": 1000},
    }
    state = {
        "ticker": "TEST",
        "company_name": "测试公司",
        "industry_name": "光通信",
        "as_of_date": "2026-07-21",
        "research_inputs": research_inputs,
        "stock_market_data": {"stock": {"valuations": []}},
    }
    state.update(business_agent.run(state, DEPS))
    state.update(profit_forecast_agent.run(state, DEPS))
    state.update(company_valuation_agent.run(state, DEPS))

    profit = state["profit_forecast_result"]
    valuation = state["company_valuation_result"]

    assert (
        profit["quarterly_analysis"]["expectation_assessment"]
        == "severely_underestimated"
    )
    assert profit["quarterly_analysis"]["inflection"] == "confirmed"
    assert profit["second_revision"]["range"] == {
        "low": Decimal("0.15"),
        "high": Decimal("0.25"),
    }
    assert profit["adjusted_forecasts"][0]["adjusted_net_profit_range"] == {
        "low": Decimal("132.2500"),
        "high": Decimal("156.2500"),
    }
    assert [item["forecast_year"] for item in valuation["annual_valuations"]] == [
        2026,
        2027,
        2028,
    ]
    assert valuation["investment_signal"]["signal"] == "strong_buy"
