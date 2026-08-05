"""LangGraph assembly for the diagram-driven stock research workflow."""

from __future__ import annotations

from functools import partial, wraps
from typing import Any, Callable, Literal

from .agents import (
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
from .dependencies import AgentDependencies
from .llm_orchestration import LLMNodeOrchestrator
from .routing import TaskType, get_execution_plan
from .state import DiagramBasedResearchState
from .contracts import RunEvent


NodeFunction = Callable[[dict[str, Any], AgentDependencies], dict[str, Any]]


def build_research_graph(
    deps: AgentDependencies,
    task_type: TaskType | str = TaskType.FULL,
    checkpointer: Any = None,
) -> Any:
    """Build and compile the workflow selected by the task execution plan."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError('LangGraph is required. Run: pip install -e ".[dev]"') from exc

    plan = get_execution_plan(task_type)
    graph = StateGraph(DiagramBasedResearchState)
    nodes: dict[str, NodeFunction] = {
        "planner": planner_agent.run,
        "industry_entry": industry_entry_agent.run,
        "industry_report": industry_report_agent.run,
        "upstream_capex": upstream_capex_agent.run,
        "policy": policy_agent.run,
        "future_capex_forecast": future_capex_forecast_agent.run,
        "industry_valuation": industry_valuation_agent.run,
        "stock_entry": stock_entry_agent.run,
        "stock_data_fetch": stock_data_fetch_agent.run,
        "stock_data_analysis": stock_data_analysis_agent.run,
        "business": business_agent.run,
        "profit_forecast": profit_forecast_agent.run,
        "marginal_change": marginal_change_agent.run,
        "company_valuation": company_valuation_agent.run,
        "stock_technical": stock_technical_agent.run,
        "market_entry": market_entry_agent.run,
        "index_analysis": index_analysis_agent.run,
        "sector_technical": sector_technical_agent.run,
        "sentiment": sentiment_agent.run,
        "research_join": research_join_agent.run,
        "decision": decision_agent.run,
        "review": review_agent.run,
        "report": report_agent.run,
    }
    llm_orchestrator = LLMNodeOrchestrator(deps, max_concurrency=3)
    for node_name in plan.enabled_nodes:
        graph.add_node(
            node_name,
            _instrument(node_name, nodes[node_name], deps, llm_orchestrator),
        )

    for source, target in plan.edges:
        resolved_source = (
            START
            if source == "__start__"
            else list(source)
            if isinstance(source, tuple)
            else source
        )
        graph.add_edge(resolved_source, target)
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"retry": "planner", "report": "report"},
    )
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


def route_after_review(state: DiagramBasedResearchState) -> Literal["retry", "report"]:
    return "retry" if state.get("review_result", {}).get("needs_retry", False) else "report"


def _instrument(
    name: str,
    function: NodeFunction,
    deps: AgentDependencies,
    llm_orchestrator: LLMNodeOrchestrator,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    @wraps(function)
    def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        run_id = str(state.get("run_id", "pending"))
        deps.events.emit(
            RunEvent(
                event_type="node",
                stage=name,
                status="started",
                message=f"节点 {name} 开始",
            )
        )
        try:
            output = function(state, deps)
            advisory = llm_orchestrator.analyze(name, state, output)
            if advisory is not None:
                output = dict(output)
                output["llm_node_results"] = {name: advisory}
                if name == "report" and "final_markdown" in output:
                    all_results = {
                        **state.get("llm_node_results", {}),
                        name: advisory,
                    }
                    output["final_markdown"] = _append_llm_audit(
                        str(output["final_markdown"]), all_results, state
                    )
                    deps.repository.save_final_report(run_id, output["final_markdown"])
            output = {**output, "completed_nodes": [name]}
            deps.repository.record_node_run(run_id, name, "completed", dict(state), output)
            deps.events.emit(
                RunEvent(
                    event_type="node",
                    stage=name,
                    status="completed",
                    message=f"节点 {name} 完成",
                )
            )
            return output
        except Exception as exc:
            failure_output = {"failed_nodes": [name]}
            deps.repository.record_node_run(
                run_id, name, "failed", dict(state), failure_output, str(exc)
            )
            deps.events.emit(
                RunEvent(
                    event_type="node",
                    stage=name,
                    status="failed",
                    message=f"节点 {name} 失败",
                    metadata={"error_type": type(exc).__name__, "failed_nodes": [name]},
                )
            )
            raise

    return wrapped


def _append_llm_audit(
    markdown: str, results: dict[str, Any], state: dict[str, Any]
) -> str:
    completed = sum(
        1 for item in results.values() if item.get("status") == "completed"
    )
    failed = len(results) - completed
    prompt_tokens = sum(
        int(item.get("usage", {}).get("prompt_tokens", 0) or 0)
        for item in results.values()
    )
    completion_tokens = sum(
        int(item.get("usage", {}).get("completion_tokens", 0) or 0)
        for item in results.values()
    )
    stock = state.get("stock_market_data", {}).get("stock", {})
    coverage = stock.get("metadata", {}) if isinstance(stock, dict) else {}
    intraday = stock.get("minute_bars", []) if isinstance(stock, dict) else []
    intraday_dates = {
        str(item.get("trade_date", ""))[:10]
        for item in intraday
        if isinstance(item, dict) and item.get("trade_date")
    }
    actual_intraday_per_day = (
        round(len(intraday) / len(intraday_dates), 2) if intraday_dates else 0
    )
    news_items = (
        state.get("research_inputs", {}).get("sentiment", {}).get("evidence", [])
    )
    news_dates = sorted(
        {
            str(item.get("published_at", ""))[:10]
            for item in news_items
            if isinstance(item, dict) and item.get("published_at")
        }
    )
    rows = [
        "## 16. D4F 节点审计",
        "",
        f"- 节点总数：{len(results)}",
        f"- 成功：{completed}",
        f"- 失败：{failed}",
        f"- 实际输入 Token：{prompt_tokens}",
        f"- 实际输出 Token：{completion_tokens}",
        (
            f"- 日线覆盖：目标 {state.get('daily_trading_days', 70)} 个交易日，"
            f"实际 {coverage.get('actual_trading_days', len(stock.get('bars', [])) if isinstance(stock, dict) else 0)} 个。"
        ),
        (
            f"- 盘中覆盖：{state.get('intraday_interval', '60m')}，目标每日 "
            f"{state.get('intraday_target_bars_per_day', 15)} 根，实际日均 {actual_intraday_per_day} 根；不插值。"
        ),
        (
            f"- 新闻覆盖：目标最多 {state.get('news_limit', 36)} 条，实际 {len(news_items)} 条，"
            f"日期跨度 {news_dates[0] if news_dates else '无'} 至 {news_dates[-1] if news_dates else '无'}。"
        ),
        "- 权威边界：所有模型输出均为辅助分析，不修改确定性指标、Decision 或 Review 路由。",
        "",
        "| 节点 | 状态 | 估算输入 Token | 实际输入 Token | 实际输出 Token | 裁剪步骤 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for node_name, item in sorted(results.items()):
        manifest = item.get("projection_manifest", {})
        usage = item.get("usage", {})
        rows.append(
            "| {node} | {status} | {estimated} | {prompt} | {completion} | {reductions} |".format(
                node=node_name,
                status=item.get("status", "unknown"),
                estimated=manifest.get("estimated_prompt_tokens", 0),
                prompt=usage.get("prompt_tokens", 0),
                completion=usage.get("completion_tokens", 0),
                reductions=len(manifest.get("reductions", [])),
            )
        )
    return markdown.rstrip() + "\n\n" + "\n".join(rows) + "\n"
