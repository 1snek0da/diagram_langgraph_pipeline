from diagram_langgraph_pipeline.agents import decision_agent, review_agent
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}))


def test_high_valuation_and_high_position_prevent_chasing():
    state = {
        "industry_trend_result": {"trend": "positive"},
        "profit_forecast_result": {"revision_direction": "up"},
        "marginal_change_result": {"direction": "positive"},
        "stock_market_data_analysis": {
            "valuation_percentile": {"pe_ttm": {"percentile": 0.92}},
            "data_coverage": {"coverage_ratio": 1.0},
        },
        "stock_technical_result": {"trend": "up", "high_position_risk": True},
        "index_analysis_result": {"risk_preference": "risk_on"},
        "sentiment_result": {"crowding_risk": "high"},
        "evidence_refs": [{}, {}, {}, {}, {}, {}],
        "missing_items": [],
        "risk_points": [],
    }

    result = decision_agent.run(state, DEPS)["decision_result"]

    assert result["action_bias"] == "hold"
    assert len(result["conflict_points"]) >= 3


def test_review_retries_then_exits_at_limit():
    state = {
        "retry_count": 0,
        "max_retries": 1,
        "stock_market_data_analysis": {"data_coverage": {"coverage_ratio": 0.2}},
        "evidence_refs": [],
    }
    first = review_agent.run(state, DEPS)
    assert first["review_result"]["needs_retry"] is True
    assert first["retry_count"] == 1

    state.update(first)
    second = review_agent.run(state, DEPS)
    assert second["review_result"]["needs_retry"] is False
    assert second["review_result"]["retry_exhausted"] is True
