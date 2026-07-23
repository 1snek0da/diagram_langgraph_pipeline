"""Shared state schema for the diagram-based research graph."""

from __future__ import annotations

from typing import Any, Literal
from typing_extensions import TypedDict


InvestmentHorizon = Literal["short", "medium", "long"]


class DiagramBasedResearchState(TypedDict, total=False):
    # Request identity
    run_id: str
    ticker: str
    company_name: str
    industry_name: str
    industry_code: str
    as_of_date: str
    investment_horizon: InvestmentHorizon
    user_request: str
    benchmark_ticker: str
    sector_index_ticker: str
    licensed_report_paths: list[str]
    policy_urls: list[str]

    # Optional caller-supplied research material keyed by topic.
    research_inputs: dict[str, Any]

    # Planning and branch entry contexts
    planner_tasks: dict[str, Any]
    industry_task_context: dict[str, Any]
    stock_task_context: dict[str, Any]
    market_task_context: dict[str, Any]

    # Industry branch
    industry_report_result: dict[str, Any]
    upstream_capex_result: dict[str, Any]
    policy_result: dict[str, Any]
    future_capex_forecast_result: dict[str, Any]
    industry_valuation_result: dict[str, Any]

    # Stock branch
    business_result: dict[str, Any]
    profit_forecast_result: dict[str, Any]
    marginal_change_result: dict[str, Any]
    stock_market_data: dict[str, Any]
    stock_market_data_analysis: dict[str, Any]
    company_valuation_result: dict[str, Any]
    stock_technical_result: dict[str, Any]

    # Market branch
    index_analysis_result: dict[str, Any]
    sector_technical_result: dict[str, Any]
    sentiment_result: dict[str, Any]

    # Synthesis, review, and output
    joined_research_result: dict[str, Any]
    decision_result: dict[str, Any]
    review_result: dict[str, Any]
    final_markdown: str
    evidence_refs: list[dict[str, Any]]
    missing_items: list[str]
    risk_points: list[str]
    retry_count: int
    max_retries: int
