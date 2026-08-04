"""Shared state schema for the diagram-based research graph."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from typing_extensions import TypedDict


InvestmentHorizon = Literal["short", "medium", "long"]


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Merge parallel node maps without losing sibling branch results."""

    return {**(left or {}), **(right or {})}


class DiagramBasedResearchState(TypedDict, total=False):
    # Request identity
    run_id: str
    ticker: str
    company_name: str
    industry_name: str
    industry_code: str
    company_cik: str
    as_of_date: str
    investment_horizon: InvestmentHorizon
    user_request: str
    benchmark_ticker: str
    sector_index_ticker: str
    market_history_days: int
    licensed_report_paths: list[str]
    policy_urls: list[str]
    run_profile: str
    daily_trading_days: int
    market_history_fallback_days: int
    technical_trading_days: int
    technical_history_days: int
    research_window_start: str
    intraday_interval: str
    intraday_target_bars_per_day: int
    intraday_recent_full_days: int
    news_limit: int
    data_acquisition_summary: dict[str, Any]
    llm_scope: str
    llm_projection: str
    llm_prompt_token_limit: int
    llm_projection_target: int
    llm_max_concurrency: int

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
    llm_advisory_result: dict[str, Any]
    llm_node_results: Annotated[dict[str, Any], merge_dicts]
    final_markdown: str
    evidence_refs: list[dict[str, Any]]
    missing_items: list[str]
    risk_points: list[str]
    retry_count: int
    max_retries: int
