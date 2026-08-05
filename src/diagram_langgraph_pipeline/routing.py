from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskType(str, Enum):
    FULL = "full"
    INDUSTRY = "industry"
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    MARKET = "market"


GraphSource = str | tuple[str, ...]
GraphEdge = tuple[GraphSource, str]


@dataclass(frozen=True)
class TaskExecutionPlan:
    task_type: TaskType
    required_nodes: tuple[str, ...]
    support_nodes: tuple[str, ...]
    optional_nodes: tuple[str, ...]
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    result_keys: tuple[str, ...]
    conclusion_scope: str
    edges: tuple[GraphEdge, ...]

    @property
    def enabled_nodes(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (*self.required_nodes, *self.support_nodes, *self.optional_nodes)
            )
        )

    @property
    def skipped_nodes(self) -> tuple[str, ...]:
        enabled = set(self.enabled_nodes)
        return tuple(name for name in ALL_NODE_NAMES if name not in enabled)


ALL_NODE_NAMES = (
    "planner",
    "industry_entry",
    "industry_report",
    "upstream_capex",
    "policy",
    "future_capex_forecast",
    "industry_valuation",
    "stock_entry",
    "stock_data_fetch",
    "stock_data_analysis",
    "business",
    "profit_forecast",
    "marginal_change",
    "company_valuation",
    "stock_technical",
    "market_entry",
    "index_analysis",
    "sector_technical",
    "sentiment",
    "research_join",
    "decision",
    "review",
    "report",
)


TASK_PLANS = {
    TaskType.FULL: TaskExecutionPlan(
        task_type=TaskType.FULL,
        required_nodes=(
            "industry_report",
            "upstream_capex",
            "policy",
            "future_capex_forecast",
            "industry_valuation",
            "stock_data_analysis",
            "business",
            "profit_forecast",
            "company_valuation",
            "stock_technical",
            "index_analysis",
            "sector_technical",
            "sentiment",
            "decision",
        ),
        support_nodes=(
            "planner",
            "industry_entry",
            "stock_entry",
            "stock_data_fetch",
            "market_entry",
            "research_join",
            "review",
            "report",
        ),
        optional_nodes=("marginal_change",),
        required_inputs=("ticker", "industry_name", "as_of_date", "investment_horizon"),
        required_outputs=(
            "industry_valuation_result",
            "business_result",
            "profit_forecast_result",
            "company_valuation_result",
            "stock_market_data_analysis",
            "stock_technical_result",
            "index_analysis_result",
            "sector_technical_result",
            "sentiment_result",
            "decision_result",
        ),
        result_keys=(
            "industry_report_result",
            "upstream_capex_result",
            "policy_result",
            "future_capex_forecast_result",
            "industry_valuation_result",
            "business_result",
            "profit_forecast_result",
            "marginal_change_result",
            "company_valuation_result",
            "stock_market_data_analysis",
            "stock_technical_result",
            "index_analysis_result",
            "sector_technical_result",
            "sentiment_result",
        ),
        conclusion_scope="完整综合研究与买卖点判断",
        edges=(
            ("__start__", "planner"),
            ("planner", "industry_entry"),
            ("planner", "stock_entry"),
            ("planner", "market_entry"),
            ("industry_entry", "industry_report"),
            ("industry_report", "upstream_capex"),
            ("industry_report", "policy"),
            (("upstream_capex", "policy"), "future_capex_forecast"),
            ("future_capex_forecast", "industry_valuation"),
            ("stock_entry", "stock_data_fetch"),
            ("stock_entry", "business"),
            ("stock_data_fetch", "stock_data_analysis"),
            ("business", "profit_forecast"),
            ("business", "marginal_change"),
            (
                ("profit_forecast", "marginal_change", "stock_data_analysis"),
                "company_valuation",
            ),
            ("stock_data_analysis", "stock_technical"),
            ("market_entry", "index_analysis"),
            ("market_entry", "sector_technical"),
            ("market_entry", "sentiment"),
            (
                (
                    "industry_valuation",
                    "company_valuation",
                    "stock_technical",
                    "stock_data_analysis",
                    "index_analysis",
                    "sector_technical",
                    "sentiment",
                ),
                "research_join",
            ),
            ("research_join", "decision"),
            ("decision", "review"),
        ),
    ),
    TaskType.INDUSTRY: TaskExecutionPlan(
        task_type=TaskType.INDUSTRY,
        required_nodes=(
            "industry_report",
            "upstream_capex",
            "policy",
            "future_capex_forecast",
            "industry_valuation",
        ),
        support_nodes=("planner", "industry_entry", "research_join", "review", "report"),
        optional_nodes=(),
        required_inputs=("industry_name", "as_of_date", "investment_horizon"),
        required_outputs=(
            "industry_report_result",
            "upstream_capex_result",
            "policy_result",
            "future_capex_forecast_result",
            "industry_valuation_result",
        ),
        result_keys=(
            "industry_report_result",
            "upstream_capex_result",
            "policy_result",
            "future_capex_forecast_result",
            "industry_valuation_result",
        ),
        conclusion_scope="仅行业研究，不给出个股买卖结论",
        edges=(
            ("__start__", "planner"),
            ("planner", "industry_entry"),
            ("industry_entry", "industry_report"),
            ("industry_report", "upstream_capex"),
            ("industry_report", "policy"),
            (("upstream_capex", "policy"), "future_capex_forecast"),
            ("future_capex_forecast", "industry_valuation"),
            ("industry_valuation", "research_join"),
            ("research_join", "review"),
        ),
    ),
    TaskType.FUNDAMENTAL: TaskExecutionPlan(
        task_type=TaskType.FUNDAMENTAL,
        required_nodes=("business", "profit_forecast", "company_valuation"),
        support_nodes=(
            "planner",
            "stock_entry",
            "stock_data_fetch",
            "research_join",
            "review",
            "report",
        ),
        optional_nodes=("marginal_change",),
        required_inputs=("ticker", "as_of_date", "investment_horizon"),
        required_outputs=(
            "business_result",
            "profit_forecast_result",
            "company_valuation_result",
        ),
        result_keys=(
            "business_result",
            "profit_forecast_result",
            "marginal_change_result",
            "company_valuation_result",
        ),
        conclusion_scope="仅个股基本面与估值，不给出完整买卖结论",
        edges=(
            ("__start__", "planner"),
            ("planner", "stock_entry"),
            ("stock_entry", "stock_data_fetch"),
            ("stock_entry", "business"),
            ("business", "profit_forecast"),
            ("business", "marginal_change"),
            (
                ("profit_forecast", "marginal_change", "stock_data_fetch"),
                "company_valuation",
            ),
            ("company_valuation", "research_join"),
            ("research_join", "review"),
        ),
    ),
    TaskType.TECHNICAL: TaskExecutionPlan(
        task_type=TaskType.TECHNICAL,
        required_nodes=("stock_data_analysis", "stock_technical"),
        support_nodes=(
            "planner",
            "stock_entry",
            "stock_data_fetch",
            "research_join",
            "review",
            "report",
        ),
        optional_nodes=(),
        required_inputs=("ticker", "as_of_date"),
        required_outputs=("stock_market_data_analysis", "stock_technical_result"),
        result_keys=("stock_market_data_analysis", "stock_technical_result"),
        conclusion_scope="仅个股技术面，不给出完整买卖结论",
        edges=(
            ("__start__", "planner"),
            ("planner", "stock_entry"),
            ("stock_entry", "stock_data_fetch"),
            ("stock_data_fetch", "stock_data_analysis"),
            ("stock_data_analysis", "stock_technical"),
            ("stock_technical", "research_join"),
            ("research_join", "review"),
        ),
    ),
    TaskType.MARKET: TaskExecutionPlan(
        task_type=TaskType.MARKET,
        required_nodes=("index_analysis", "sector_technical", "sentiment"),
        support_nodes=("planner", "market_entry", "research_join", "review", "report"),
        optional_nodes=(),
        required_inputs=("as_of_date",),
        required_outputs=(
            "index_analysis_result",
            "sector_technical_result",
            "sentiment_result",
        ),
        result_keys=(
            "index_analysis_result",
            "sector_technical_result",
            "sentiment_result",
        ),
        conclusion_scope="仅市场环境，不给出个股买卖结论",
        edges=(
            ("__start__", "planner"),
            ("planner", "market_entry"),
            ("market_entry", "index_analysis"),
            ("market_entry", "sector_technical"),
            ("market_entry", "sentiment"),
            (("index_analysis", "sector_technical", "sentiment"), "research_join"),
            ("research_join", "review"),
        ),
    ),
}


def get_execution_plan(task_type: TaskType | str) -> TaskExecutionPlan:
    try:
        normalized = task_type if isinstance(task_type, TaskType) else TaskType(task_type)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in TaskType)
        raise ValueError(
            f"Unsupported task type {task_type!r}; choose one of: {allowed}"
        ) from exc
    return TASK_PLANS[normalized]
