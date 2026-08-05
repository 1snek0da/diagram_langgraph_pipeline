import pytest

from diagram_langgraph_pipeline.agents import report_agent, research_join_agent
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}), llm=None)


def test_research_join_uses_only_selected_result_keys_and_selected_gaps():
    state = {
        "task_type": "technical",
        "result_keys": ["stock_market_data_analysis", "stock_technical_result"],
        "conclusion_scope": "仅个股技术面，不给出完整买卖结论",
        "stock_market_data_analysis": {
            "evidence": [{"claim_text": "selected market evidence"}],
            "data_coverage": {"missing_items": ["selected market gap"]},
        },
        "stock_technical_result": {
            "evidence": [{"claim_text": "selected technical evidence"}],
            "missing_items": ["selected technical gap"],
        },
        "industry_report_result": {
            "evidence": [{"claim_text": "out-of-scope evidence"}],
            "missing_items": ["out-of-scope gap"],
        },
        "business_result": {"risks": ["out-of-scope risk"]},
    }

    result = research_join_agent.run(state, DEPS)
    joined = result["joined_research_result"]

    assert joined["task_type"] == "technical"
    assert joined["conclusion_scope"] == state["conclusion_scope"]
    assert set(joined["selected_results"]) == set(state["result_keys"])
    assert "industry_report_result" not in joined["selected_results"]
    assert [item["claim_text"] for item in result["evidence_refs"]] == [
        "selected market evidence",
        "selected technical evidence",
    ]
    assert result["missing_items"] == [
        "selected market gap",
        "selected technical gap",
    ]
    assert "out-of-scope risk" not in result["risk_points"]


def test_research_join_ignores_gaps_from_a_skipped_optional_result():
    state = {
        "task_type": "fundamental",
        "result_keys": ["business_result", "marginal_change_result"],
        "business_result": {"evidence": [{"claim_text": "business"}]},
        "marginal_change_result": {
            "status": "skipped",
            "missing_items": ["no marginal-change source"],
        },
        "optional_node_statuses": {
            "marginal_change": {"status": "skipped", "reason": "no trusted source"}
        },
    }

    result = research_join_agent.run(state, DEPS)

    assert result["missing_items"] == []
    assert result["evidence_refs"] == [{"claim_text": "business"}]


@pytest.mark.parametrize(
    ("task_type", "conclusion_scope", "state_results", "present", "absent"),
    [
        (
            "industry",
            "仅行业研究，不给出个股买卖结论",
            {
                "industry_report_result": {"summary": "industry-only"},
                "upstream_capex_result": {"trend": "up"},
                "policy_result": {"direction": "supportive"},
                "future_capex_forecast_result": {"trend": "positive"},
                "industry_valuation_result": {"scenarios": []},
            },
            ["行业研究结论", "行业分析", "未来资本开支预测与行业价值测算"],
            ["盈利预测与估值测算", "个股技术形态分析", "市场情绪分析"],
        ),
        (
            "fundamental",
            "仅个股基本面与估值，不给出完整买卖结论",
            {
                "business_result": {"summary": "fundamental-only"},
                "profit_forecast_result": {"forecasts": []},
                "marginal_change_result": {"status": "skipped"},
                "company_valuation_result": {"scenarios": []},
            },
            ["基本面与估值结论", "公司业务与行业增长匹配度", "盈利预测与估值测算"],
            ["行业分析", "个股技术形态分析", "市场情绪分析"],
        ),
        (
            "technical",
            "仅个股技术面，不给出完整买卖结论",
            {
                "stock_market_data_analysis": {"summary": "technical-only"},
                "stock_technical_result": {"trend": "up"},
            },
            ["技术面结论", "个股股市数据分析", "个股技术形态分析"],
            ["行业分析", "盈利预测与估值测算", "市场情绪分析"],
        ),
        (
            "market",
            "仅市场环境，不给出个股买卖结论",
            {
                "index_analysis_result": {"summary": "market-only"},
                "sector_technical_result": {"trend": "up"},
                "sentiment_result": {"crowding_risk": "low"},
            },
            ["市场环境结论", "大盘与板块环境", "市场情绪分析"],
            ["行业分析", "盈利预测与估值测算", "个股技术形态分析"],
        ),
    ],
)
def test_partial_report_discloses_scope_and_renders_only_task_sections(
    task_type, conclusion_scope, state_results, present, absent
):
    state = {
        "run_id": f"run-{task_type}",
        "task_type": task_type,
        "ticker": "AAPL",
        "company_name": "Apple",
        "as_of_date": "2026-08-05",
        "investment_horizon": "short",
        "required_nodes": ["required-node"],
        "support_nodes": ["planner", "research_join", "review", "report"],
        "optional_nodes": [],
        "skipped_nodes": ["decision"],
        "completed_nodes": ["required-node"],
        "failed_nodes": [],
        "conclusion_scope": conclusion_scope,
        "decision_result": {
            "action_bias": "buy",
            "summary": "FORBIDDEN_FULL_DECISION",
        },
        "review_result": {"passed": True},
        "evidence_refs": [],
        "missing_items": [],
        **state_results,
    }

    markdown = report_agent.run(state, DEPS)["final_markdown"]

    assert "任务执行范围" in markdown
    assert conclusion_scope in markdown
    for title in present:
        assert title in markdown
    for title in absent:
        assert title not in markdown
    assert "综合买卖点判断" not in markdown
    assert "FORBIDDEN_FULL_DECISION" not in markdown
    assert "**决策倾向**：buy" not in markdown
    assert markdown.index("任务执行范围") < markdown.index(present[0])
    assert "主要风险与失效条件" in markdown
    assert "证据引用与数据缺口" in markdown
    assert "Reflection 校验结果" in markdown
