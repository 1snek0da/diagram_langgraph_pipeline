from diagram_langgraph_pipeline.agents import decision_agent, review_agent
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}))


def test_high_valuation_and_high_position_prevent_chasing():
    state = {
        "future_capex_forecast_result": {"trend": "positive"},
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


def test_technical_review_does_not_require_other_task_results_or_evidence():
    state = {
        "task_type": "technical",
        "required_outputs": [
            "stock_market_data_analysis",
            "stock_technical_result",
        ],
        "stock_market_data_analysis": {
            "data_coverage": {"coverage_ratio": 1.0}
        },
        "stock_technical_result": {"trend": "up", "missing_items": []},
        "evidence_refs": [],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is False
    assert "缺少行业价值测算" not in result["missing_items"]
    assert "缺少综合决策" not in result["missing_items"]


def test_industry_review_uses_industry_coverage_without_market_coverage():
    required_outputs = [
        "industry_report_result",
        "upstream_capex_result",
        "policy_result",
        "future_capex_forecast_result",
        "industry_valuation_result",
    ]
    state = {
        "task_type": "industry",
        "required_outputs": required_outputs,
        **{key: {"status": "completed"} for key in required_outputs},
        "upstream_capex_result": {
            "status": "completed",
            "company_coverage": {"coverage_ratio": 0.6},
        },
        "evidence_refs": [{}, {}, {}],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is False


def test_fundamental_review_treats_skipped_marginal_change_as_informational():
    state = {
        "task_type": "fundamental",
        "required_outputs": [
            "business_result",
            "profit_forecast_result",
            "company_valuation_result",
        ],
        "business_result": {"evidence": [{}]},
        "profit_forecast_result": {"evidence": [{}]},
        "company_valuation_result": {"evidence": [{}]},
        "result_keys": [
            "business_result",
            "profit_forecast_result",
            "marginal_change_result",
            "company_valuation_result",
        ],
        "optional_nodes": ["marginal_change"],
        "optional_node_statuses": {
            "marginal_change": {"status": "skipped", "reason": "no trusted source"}
        },
        "evidence_refs": [{}, {}, {}],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is False
    assert "marginal_change_result" not in result["missing_items"]
    assert all(
        task.get("node") != "marginal_change"
        for task in result["retry_tasks"]
        if isinstance(task, dict)
    )


def test_market_review_requires_market_results_and_evidence_only():
    state = {
        "task_type": "market",
        "required_outputs": [
            "index_analysis_result",
            "sector_technical_result",
            "sentiment_result",
        ],
        "index_analysis_result": {"risk_preference": "risk_on"},
        "sector_technical_result": {"trend": "up"},
        "sentiment_result": {"crowding_risk": "low"},
        "evidence_refs": [{}, {}, {}],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is False


def test_review_creates_structured_retry_for_missing_required_output():
    state = {
        "task_type": "technical",
        "required_outputs": [
            "stock_market_data_analysis",
            "stock_technical_result",
        ],
        "required_nodes": ["stock_data_analysis", "stock_technical"],
        "stock_market_data_analysis": {
            "data_coverage": {"coverage_ratio": 1.0}
        },
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is True
    assert result["retry_tasks"] == [
        {
            "node": "stock_technical",
            "result_key": "stock_technical_result",
            "reason": "缺少必需结果：stock_technical_result",
        }
    ]
