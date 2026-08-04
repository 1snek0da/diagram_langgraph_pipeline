from diagram_langgraph_pipeline.agents import (
    business_agent,
    company_valuation_agent,
    decision_agent,
    index_analysis_agent,
    industry_entry_agent,
    industry_report_agent,
    future_capex_forecast_agent,
    industry_valuation_agent,
    marginal_change_agent,
    market_entry_agent,
    planner_agent,
    policy_agent,
    profit_forecast_agent,
    report_agent,
    research_join_agent,
    review_agent,
    sector_technical_agent,
    sentiment_agent,
    stock_data_analysis_agent,
    stock_data_fetch_agent,
    stock_entry_agent,
    stock_technical_agent,
    upstream_capex_agent,
)
from diagram_langgraph_pipeline.demo_data import demo_research_inputs, make_market_payload
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


def test_all_agent_contracts_form_a_complete_report():
    payloads = {
        "STOCK": make_market_payload(20.0, 0.0010),
        "BENCH": make_market_payload(100.0, 0.0003),
        "SECTOR": make_market_payload(50.0, 0.0006),
    }
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider(payloads))
    state = {
        "ticker": "STOCK",
        "company_name": "示例公司",
        "industry_name": "示例行业",
        "as_of_date": "2026-07-21",
        "investment_horizon": "medium",
        "benchmark_ticker": "BENCH",
        "sector_index_ticker": "SECTOR",
        "research_inputs": demo_research_inputs(),
        "retry_count": 0,
        "max_retries": 0,
    }
    ordered_nodes = [
        planner_agent.run,
        industry_entry_agent.run,
        stock_entry_agent.run,
        market_entry_agent.run,
        industry_report_agent.run,
        upstream_capex_agent.run,
        policy_agent.run,
        future_capex_forecast_agent.run,
        industry_valuation_agent.run,
        stock_data_fetch_agent.run,
        stock_data_analysis_agent.run,
        business_agent.run,
        profit_forecast_agent.run,
        marginal_change_agent.run,
        company_valuation_agent.run,
        stock_technical_agent.run,
        index_analysis_agent.run,
        sector_technical_agent.run,
        sentiment_agent.run,
        research_join_agent.run,
        decision_agent.run,
        review_agent.run,
        report_agent.run,
    ]
    for node in ordered_nodes:
        state.update(node(state, deps))

    assert state["decision_result"]["action_bias"] in {"buy", "hold", "watch", "reduce", "sell"}
    assert "## 8. 个股股市数据分析" in state["final_markdown"]
    assert "## 15. Reflection 校验结果" in state["final_markdown"]
    assert "本报告仅用于研究辅助，不构成投资建议" in state["final_markdown"]
