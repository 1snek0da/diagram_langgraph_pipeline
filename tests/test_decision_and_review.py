import pytest

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


def test_required_output_on_skipped_node_still_fails_without_retrying_node():
    state = {
        "task_type": "technical",
        "required_outputs": [
            "stock_market_data_analysis",
            "stock_technical_result",
        ],
        "skipped_nodes": ["stock_technical"],
        "stock_market_data_analysis": {
            "data_coverage": {"coverage_ratio": 1.0}
        },
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is True
    assert "缺少必需结果：stock_technical_result" in result["missing_items"]
    assert result["retry_tasks"] == []


def test_market_coverage_gap_retries_stock_data_analysis_node():
    state = {
        "task_type": "technical",
        "required_outputs": [
            "stock_market_data_analysis",
            "stock_technical_result",
        ],
        "stock_market_data_analysis": {
            "data_coverage": {"coverage_ratio": 0.2}
        },
        "stock_technical_result": {"trend": "up"},
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["retry_tasks"] == [
        {
            "node": "stock_data_analysis",
            "result_key": "stock_market_data_analysis",
            "reason": "个股市场数据覆盖率低于 0.8",
        }
    ]


def test_industry_coverage_gap_retries_upstream_capex_node():
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
            "company_coverage": {"coverage_ratio": 0.2},
        },
        "evidence_refs": [{}, {}, {}],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["retry_tasks"] == [
        {
            "node": "upstream_capex",
            "result_key": "upstream_capex_result",
            "reason": "行业公司覆盖率低于 0.6",
        }
    ]


@pytest.mark.parametrize(
    ("task_type", "skipped_node", "state"),
    [
        (
            "technical",
            "stock_data_analysis",
            {
                "required_outputs": [
                    "stock_market_data_analysis",
                    "stock_technical_result",
                ],
                "stock_market_data_analysis": {
                    "data_coverage": {"coverage_ratio": 0.2}
                },
                "stock_technical_result": {"trend": "up"},
            },
        ),
        (
            "industry",
            "upstream_capex",
            {
                "required_outputs": [
                    "industry_report_result",
                    "upstream_capex_result",
                    "policy_result",
                    "future_capex_forecast_result",
                    "industry_valuation_result",
                ],
                "industry_report_result": {"status": "completed"},
                "upstream_capex_result": {
                    "company_coverage": {"coverage_ratio": 0.2}
                },
                "policy_result": {"status": "completed"},
                "future_capex_forecast_result": {"status": "completed"},
                "industry_valuation_result": {"status": "completed"},
                "evidence_refs": [{}, {}, {}],
            },
        ),
    ],
)
def test_coverage_gap_still_fails_but_does_not_retry_skipped_node(
    task_type, skipped_node, state
):
    result = review_agent.run(
        {
            "task_type": task_type,
            "skipped_nodes": [skipped_node],
            "retry_count": 0,
            "max_retries": 1,
            **state,
        },
        DEPS,
    )["review_result"]

    assert result["needs_retry"] is True
    assert result["retry_tasks"] == []


def test_partial_logic_score_does_not_read_full_decision_result():
    state = {
        "task_type": "technical",
        "required_outputs": [
            "stock_market_data_analysis",
            "stock_technical_result",
        ],
        "stock_market_data_analysis": {
            "data_coverage": {"coverage_ratio": 1.0}
        },
        "stock_technical_result": {"trend": "up"},
    }

    without_decision = review_agent.run(state, DEPS)["review_result"]["logic_score"]
    with_decision = review_agent.run(
        {**state, "decision_result": {"conflict_points": []}}, DEPS
    )["review_result"]["logic_score"]

    assert with_decision == without_decision


def test_unknown_required_output_fails_with_safe_string_retry():
    state = {
        "task_type": "technical",
        "required_outputs": [
            "stock_market_data_analysis",
            "stock_technical_result",
            "custom_result",
        ],
        "stock_market_data_analysis": {
            "data_coverage": {"coverage_ratio": 1.0}
        },
        "stock_technical_result": {"trend": "up"},
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is True
    assert "缺少必需结果：custom_result" in result["missing_items"]
    assert result["retry_tasks"] == ["补采：缺少必需结果：custom_result"]


def test_skipped_optional_result_stale_gaps_are_removed_from_review():
    stale_gaps = ["no trusted marginal event", "marginal source coverage gap"]
    state = {
        "task_type": "fundamental",
        "required_outputs": [
            "business_result",
            "profit_forecast_result",
            "company_valuation_result",
        ],
        "business_result": {"summary": "business"},
        "profit_forecast_result": {"summary": "forecast"},
        "company_valuation_result": {"summary": "valuation"},
        "marginal_change_result": {
            "status": "skipped",
            "missing_items": [stale_gaps[0]],
            "coverage": {"missing_items": [stale_gaps[1]]},
        },
        "optional_node_statuses": {
            "marginal_change": {"status": "skipped", "reason": "no trusted source"}
        },
        "missing_items": stale_gaps,
        "evidence_refs": [{}, {}, {}],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["passed"] is True
    assert all(item not in result["missing_items"] for item in stale_gaps)
    assert result["retry_tasks"] == []


def test_passed_review_has_no_retry_tasks_for_non_blocking_gap():
    state = {
        "task_type": "fundamental",
        "required_outputs": [
            "business_result",
            "profit_forecast_result",
            "company_valuation_result",
        ],
        "business_result": {"summary": "business"},
        "profit_forecast_result": {"summary": "forecast"},
        "company_valuation_result": {"summary": "valuation"},
        "missing_items": ["non-blocking task-scoped gap"],
        "evidence_refs": [{}, {}, {}],
        "retry_count": 0,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["passed"] is True
    assert result["needs_retry"] is False
    assert result["retry_tasks"] == []


def test_retry_exhausted_review_has_no_retry_tasks():
    state = {
        "task_type": "technical",
        "required_outputs": [
            "stock_market_data_analysis",
            "stock_technical_result",
        ],
        "stock_market_data_analysis": {
            "data_coverage": {"coverage_ratio": 0.2}
        },
        "stock_technical_result": {"trend": "up"},
        "retry_count": 1,
        "max_retries": 1,
    }

    result = review_agent.run(state, DEPS)["review_result"]

    assert result["needs_retry"] is False
    assert result["retry_exhausted"] is True
    assert result["retry_tasks"] == []
