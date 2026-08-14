# Task Router and CLI Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit `full`, `industry`, `fundamental`, `technical`, and `market` task selection so each run builds only the required LangGraph nodes, applies task-scoped Review/report rules, and displays the execution scope clearly in the CLI.

**Architecture:** A deep `routing` module maps one `TaskType` to an immutable `TaskExecutionPlan` containing enabled nodes, node roles, required outputs, input requirements, conclusion scope, and graph edges. `runner` resolves the plan before graph construction and stores its public audit fields in State; graph assembly, Planner, Review, report, service, and CLI all consume that same plan instead of maintaining separate routing lists. `marginal_change` remains an optional attempted node: expected data unavailability produces a structured skipped/degraded result, while programming and contract errors still fail the run.

**Tech Stack:** Python 3.10+, LangGraph 1.2+, TypedDict/typing-extensions, Typer, Rich, pytest 8+

## Global Constraints

- Task selection is explicit; Router must not call an LLM or infer a task from natural language.
- Supported task values are exactly `full`, `industry`, `fundamental`, `technical`, and `market`.
- Omitting `--task` defaults to `full` and preserves the existing full-research behavior.
- Disabled nodes are not compiled, scheduled, audited as started/completed, allowed to call Providers, or allowed to call the LLM.
- Only `full` runs `decision` and emits a complete buy/hold/watch/reduce/sell conclusion.
- Review retries must reuse the original `task_type` and execution plan.
- Expected marginal-change data unavailability may be skipped; programming errors and schema/contract errors must propagate.
- Progress output goes to stderr; `--json` emits one stable JSON document to stdout.
- Frontend web work, natural-language task classification, manual per-node selection, and broker execution are out of scope.
- Use the project virtual environment for every command: `.venv\Scripts\python.exe`.
- On this Windows workspace, give pytest a writable base temp under the repository.

---

## File Structure

- Create `src/diagram_langgraph_pipeline/routing.py`: authoritative task enum, execution-plan model, five task plans, and lookup interface.
- Modify `src/diagram_langgraph_pipeline/state.py`: route audit fields and parallel-safe reducers.
- Modify `src/diagram_langgraph_pipeline/graph.py`: compile only plan nodes/edges and report optional-node degradation.
- Modify `src/diagram_langgraph_pipeline/runner.py`: resolve/inject one plan before graph construction and retain it across retries.
- Modify `src/diagram_langgraph_pipeline/agents/planner_agent.py`: emit only current-task work.
- Modify `src/diagram_langgraph_pipeline/agents/marginal_change_agent.py`: structured optional skip semantics.
- Modify `src/diagram_langgraph_pipeline/agents/research_join_agent.py`: aggregate only plan result keys.
- Modify `src/diagram_langgraph_pipeline/agents/review_agent.py`: task-scoped required outputs and coverage checks.
- Modify `src/diagram_langgraph_pipeline/agents/report_agent.py`: task-scoped sections and execution-scope disclosure.
- Modify `src/diagram_langgraph_pipeline/service.py`: task-aware input validation, data preparation, and result summary.
- Modify `src/diagram_langgraph_pipeline/cli.py`: `--task`, conditional wizard prompts, plan preview, and progress display.
- Create `tests/test_routing.py`: execution-plan contract tests.
- Modify `tests/test_graph.py`: node/edge selection tests.
- Modify `tests/test_decision_and_review.py`: task-specific Review tests.
- Modify `tests/test_cli.py`: CLI option, output, and display tests.
- Create `tests/test_task_router_pipeline.py`: five-mode end-to-end tests using deterministic data.
- Modify `README.md`: task modes and examples.

---

### Task 1: Authoritative Task Router Module

**Files:**
- Create: `src/diagram_langgraph_pipeline/routing.py`
- Create: `tests/test_routing.py`

**Interfaces:**
- Produces: `TaskType(str, Enum)` with five values.
- Produces: `TaskExecutionPlan` immutable dataclass.
- Produces: `get_execution_plan(task_type: TaskType | str) -> TaskExecutionPlan`.
- Produces: `ALL_NODE_NAMES: tuple[str, ...]`.
- Consumes: no application modules; this is the authoritative seam.

- [ ] **Step 1: Write failing routing contract tests**

```python
# tests/test_routing.py
import pytest

from diagram_langgraph_pipeline.routing import (
    ALL_NODE_NAMES,
    TaskType,
    get_execution_plan,
)


@pytest.mark.parametrize("task_type", list(TaskType))
def test_every_task_has_a_closed_execution_plan(task_type):
    plan = get_execution_plan(task_type)
    enabled = set(plan.enabled_nodes)
    classified = set(plan.required_nodes) | set(plan.support_nodes) | set(plan.optional_nodes)
    assert classified == enabled
    assert not (set(plan.required_nodes) & set(plan.support_nodes))
    assert not (set(plan.required_nodes) & set(plan.optional_nodes))
    assert not (set(plan.support_nodes) & set(plan.optional_nodes))
    assert set(plan.skipped_nodes) == set(ALL_NODE_NAMES) - enabled
    assert "planner" in enabled
    assert "research_join" in enabled
    assert "review" in enabled
    assert "report" in enabled
    for source, target in plan.edges:
        sources = source if isinstance(source, tuple) else (source,)
        assert set(sources) - {"__start__"} <= enabled
        assert target in enabled


def test_only_full_enables_decision():
    assert "decision" in get_execution_plan(TaskType.FULL).enabled_nodes
    for task_type in TaskType:
        if task_type is not TaskType.FULL:
            assert "decision" not in get_execution_plan(task_type).enabled_nodes


def test_fundamental_attempts_marginal_change_as_optional():
    plan = get_execution_plan("fundamental")
    assert "marginal_change" in plan.optional_nodes
    assert "company_valuation_result" in plan.required_outputs
    assert "stock_technical" in plan.skipped_nodes


def test_unknown_task_is_rejected():
    with pytest.raises(ValueError, match="Unsupported task type"):
        get_execution_plan("unknown")
```

- [ ] **Step 2: Run tests and verify the module is missing**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_routing.py -q --basetemp .pytest-tmp/task1-red
```

Expected: collection fails with `ModuleNotFoundError: diagram_langgraph_pipeline.routing`.

- [ ] **Step 3: Implement the routing interface and five immutable plans**

Create `routing.py` with this public shape:

```python
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
        return tuple(dict.fromkeys((*self.required_nodes, *self.support_nodes, *self.optional_nodes)))

    @property
    def skipped_nodes(self) -> tuple[str, ...]:
        enabled = set(self.enabled_nodes)
        return tuple(name for name in ALL_NODE_NAMES if name not in enabled)


ALL_NODE_NAMES = (
    "planner", "industry_entry", "industry_report", "upstream_capex", "policy",
    "future_capex_forecast", "industry_valuation", "stock_entry", "stock_data_fetch",
    "stock_data_analysis", "business", "profit_forecast", "marginal_change",
    "company_valuation", "stock_technical", "market_entry", "index_analysis",
    "sector_technical", "sentiment", "research_join", "decision", "review", "report",
)
```

Define all five plans in one `TASK_PLANS` mapping. Use `"__start__"` as the start sentinel. The following table is authoritative; do not duplicate or reinterpret these lists in graph, service, or CLI modules:

```python
TASK_PLANS = {
    TaskType.FULL: TaskExecutionPlan(
        task_type=TaskType.FULL,
        required_nodes=(
            "industry_report", "upstream_capex", "policy",
            "future_capex_forecast", "industry_valuation",
            "stock_data_analysis", "business", "profit_forecast",
            "company_valuation", "stock_technical", "index_analysis",
            "sector_technical", "sentiment", "decision",
        ),
        support_nodes=(
            "planner", "industry_entry", "stock_entry", "stock_data_fetch",
            "market_entry", "research_join", "review", "report",
        ),
        optional_nodes=("marginal_change",),
        required_inputs=("ticker", "industry_name", "as_of_date", "investment_horizon"),
        required_outputs=(
            "industry_valuation_result", "business_result",
            "profit_forecast_result", "company_valuation_result",
            "stock_market_data_analysis", "stock_technical_result",
            "index_analysis_result", "sector_technical_result",
            "sentiment_result", "decision_result",
        ),
        result_keys=(
            "industry_report_result", "upstream_capex_result", "policy_result",
            "future_capex_forecast_result", "industry_valuation_result",
            "business_result", "profit_forecast_result", "marginal_change_result",
            "company_valuation_result", "stock_market_data_analysis",
            "stock_technical_result", "index_analysis_result",
            "sector_technical_result", "sentiment_result",
        ),
        conclusion_scope="完整综合研究与买卖点判断",
        edges=(
            ("__start__", "planner"),
            ("planner", "industry_entry"), ("planner", "stock_entry"),
            ("planner", "market_entry"),
            ("industry_entry", "industry_report"),
            ("industry_report", "upstream_capex"),
            ("industry_report", "policy"),
            (("upstream_capex", "policy"), "future_capex_forecast"),
            ("future_capex_forecast", "industry_valuation"),
            ("stock_entry", "stock_data_fetch"), ("stock_entry", "business"),
            ("stock_data_fetch", "stock_data_analysis"),
            ("business", "profit_forecast"), ("business", "marginal_change"),
            (("profit_forecast", "marginal_change", "stock_data_analysis"), "company_valuation"),
            ("stock_data_analysis", "stock_technical"),
            ("market_entry", "index_analysis"),
            ("market_entry", "sector_technical"),
            ("market_entry", "sentiment"),
            ((
                "industry_valuation", "company_valuation", "stock_technical",
                "stock_data_analysis", "index_analysis", "sector_technical", "sentiment",
            ), "research_join"),
            ("research_join", "decision"), ("decision", "review"),
        ),
    ),
    TaskType.INDUSTRY: TaskExecutionPlan(
        task_type=TaskType.INDUSTRY,
        required_nodes=(
            "industry_report", "upstream_capex", "policy",
            "future_capex_forecast", "industry_valuation",
        ),
        support_nodes=("planner", "industry_entry", "research_join", "review", "report"),
        optional_nodes=(),
        required_inputs=("industry_name", "as_of_date", "investment_horizon"),
        required_outputs=(
            "industry_report_result", "upstream_capex_result", "policy_result",
            "future_capex_forecast_result", "industry_valuation_result",
        ),
        result_keys=(
            "industry_report_result", "upstream_capex_result", "policy_result",
            "future_capex_forecast_result", "industry_valuation_result",
        ),
        conclusion_scope="仅行业研究，不给出个股买卖结论",
        edges=(
            ("__start__", "planner"), ("planner", "industry_entry"),
            ("industry_entry", "industry_report"),
            ("industry_report", "upstream_capex"), ("industry_report", "policy"),
            (("upstream_capex", "policy"), "future_capex_forecast"),
            ("future_capex_forecast", "industry_valuation"),
            ("industry_valuation", "research_join"), ("research_join", "review"),
        ),
    ),
    TaskType.FUNDAMENTAL: TaskExecutionPlan(
        task_type=TaskType.FUNDAMENTAL,
        required_nodes=("business", "profit_forecast", "company_valuation"),
        support_nodes=(
            "planner", "stock_entry", "stock_data_fetch", "research_join", "review", "report",
        ),
        optional_nodes=("marginal_change",),
        required_inputs=("ticker", "as_of_date", "investment_horizon"),
        required_outputs=("business_result", "profit_forecast_result", "company_valuation_result"),
        result_keys=(
            "business_result", "profit_forecast_result", "marginal_change_result",
            "company_valuation_result",
        ),
        conclusion_scope="仅个股基本面与估值，不给出完整买卖结论",
        edges=(
            ("__start__", "planner"), ("planner", "stock_entry"),
            ("stock_entry", "stock_data_fetch"), ("stock_entry", "business"),
            ("business", "profit_forecast"), ("business", "marginal_change"),
            (("profit_forecast", "marginal_change", "stock_data_fetch"), "company_valuation"),
            ("company_valuation", "research_join"), ("research_join", "review"),
        ),
    ),
    TaskType.TECHNICAL: TaskExecutionPlan(
        task_type=TaskType.TECHNICAL,
        required_nodes=("stock_data_analysis", "stock_technical"),
        support_nodes=(
            "planner", "stock_entry", "stock_data_fetch", "research_join", "review", "report",
        ),
        optional_nodes=(),
        required_inputs=("ticker", "as_of_date"),
        required_outputs=("stock_market_data_analysis", "stock_technical_result"),
        result_keys=("stock_market_data_analysis", "stock_technical_result"),
        conclusion_scope="仅个股技术面，不给出完整买卖结论",
        edges=(
            ("__start__", "planner"), ("planner", "stock_entry"),
            ("stock_entry", "stock_data_fetch"),
            ("stock_data_fetch", "stock_data_analysis"),
            ("stock_data_analysis", "stock_technical"),
            ("stock_technical", "research_join"), ("research_join", "review"),
        ),
    ),
    TaskType.MARKET: TaskExecutionPlan(
        task_type=TaskType.MARKET,
        required_nodes=("index_analysis", "sector_technical", "sentiment"),
        support_nodes=("planner", "market_entry", "research_join", "review", "report"),
        optional_nodes=(),
        required_inputs=("as_of_date",),
        required_outputs=("index_analysis_result", "sector_technical_result", "sentiment_result"),
        result_keys=("index_analysis_result", "sector_technical_result", "sentiment_result"),
        conclusion_scope="仅市场环境，不给出个股买卖结论",
        edges=(
            ("__start__", "planner"), ("planner", "market_entry"),
            ("market_entry", "index_analysis"),
            ("market_entry", "sector_technical"), ("market_entry", "sentiment"),
            (("index_analysis", "sector_technical", "sentiment"), "research_join"),
            ("research_join", "review"),
        ),
    ),
}
```

`fundamental` waits for `(profit_forecast, marginal_change, stock_data_fetch)` before company valuation. The optional marginal-change node therefore either completes or returns its structured skip before valuation continues. Partial plans intentionally omit `decision`.

Lookup implementation:

```python
def get_execution_plan(task_type: TaskType | str) -> TaskExecutionPlan:
    try:
        normalized = task_type if isinstance(task_type, TaskType) else TaskType(task_type)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in TaskType)
        raise ValueError(f"Unsupported task type {task_type!r}; choose one of: {allowed}") from exc
    return TASK_PLANS[normalized]
```

- [ ] **Step 4: Run routing tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_routing.py -q --basetemp .pytest-tmp/task1-green
```

Expected: all tests in `tests/test_routing.py` pass.

- [ ] **Step 5: Commit the routing seam**

```powershell
git add src/diagram_langgraph_pipeline/routing.py tests/test_routing.py
git commit -m "feat: define task execution plans"
```

---

### Task 2: Plan-Driven State, Graph Assembly, and Planner

**Files:**
- Modify: `src/diagram_langgraph_pipeline/state.py:11-92`
- Modify: `src/diagram_langgraph_pipeline/graph.py:39-128`
- Modify: `src/diagram_langgraph_pipeline/runner.py:14-34`
- Modify: `src/diagram_langgraph_pipeline/agents/planner_agent.py:11-41`
- Modify: `tests/test_graph.py`

**Interfaces:**
- Consumes: `get_execution_plan()` and `TaskExecutionPlan` from Task 1.
- Produces: `build_research_graph(deps, task_type=TaskType.FULL, checkpointer=None)`.
- Produces State fields: `task_type`, node-role lists, `required_outputs`, `result_keys`, `conclusion_scope`, `completed_nodes`, `failed_nodes`, and `optional_node_statuses`.

- [ ] **Step 1: Add failing graph-selection tests**

```python
# append to tests/test_graph.py
from diagram_langgraph_pipeline.routing import TaskType, get_execution_plan


@pytest.mark.parametrize("task_type", list(TaskType))
def test_graph_contains_exactly_the_selected_task_nodes(task_type):
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    graph = build_research_graph(deps, task_type=task_type)
    actual = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    assert actual == set(get_execution_plan(task_type).enabled_nodes)


def test_technical_graph_does_not_compile_research_or_market_nodes():
    deps = AgentDependencies(market_data=InMemoryMarketDataProvider({}))
    graph = build_research_graph(deps, task_type="technical")
    nodes = set(graph.get_graph().nodes)
    assert "stock_technical" in nodes
    assert "industry_report" not in nodes
    assert "business" not in nodes
    assert "sentiment" not in nodes
    assert "decision" not in nodes
```

- [ ] **Step 2: Run the new graph tests and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_graph.py -q --basetemp .pytest-tmp/task2-red
```

Expected: FAIL because `build_research_graph` does not accept `task_type` and always compiles 23 nodes.

- [ ] **Step 3: Add parallel-safe audit reducers and State fields**

Add to `state.py`:

```python
def merge_unique(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*(left or []), *(right or [])]))


class DiagramBasedResearchState(TypedDict, total=False):
    task_type: str
    required_nodes: list[str]
    support_nodes: list[str]
    optional_nodes: list[str]
    skipped_nodes: list[str]
    required_inputs: list[str]
    required_outputs: list[str]
    result_keys: list[str]
    conclusion_scope: str
    completed_nodes: Annotated[list[str], merge_unique]
    failed_nodes: Annotated[list[str], merge_unique]
    optional_node_statuses: Annotated[dict[str, Any], merge_dicts]
```

Keep the existing State fields unchanged.

- [ ] **Step 4: Replace fixed graph assembly with plan-driven assembly**

Change the interface and use the plan edge table:

```python
def build_research_graph(
    deps: AgentDependencies,
    task_type: TaskType | str = TaskType.FULL,
    checkpointer: Any = None,
) -> Any:
    plan = get_execution_plan(task_type)
    graph = StateGraph(DiagramBasedResearchState)
    for node_name in plan.enabled_nodes:
        graph.add_node(node_name, _instrument(node_name, nodes[node_name], deps, llm_orchestrator))
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
```

The plan edges must stop at `review`; do not duplicate `review -> report` or `report -> END` in `routing.py`.

- [ ] **Step 5: Inject the plan once in runner and preserve it across retries**

In `run_research`:

```python
plan = get_execution_plan(initial_state.get("task_type", TaskType.FULL))
prepared_state = apply_run_profile(initial_state)
prepared_state.update(
    {
        "task_type": plan.task_type.value,
        "required_nodes": list(plan.required_nodes),
        "support_nodes": list(plan.support_nodes),
        "optional_nodes": list(plan.optional_nodes),
        "skipped_nodes": list(plan.skipped_nodes),
        "required_inputs": list(plan.required_inputs),
        "required_outputs": list(plan.required_outputs),
        "result_keys": list(plan.result_keys),
        "conclusion_scope": plan.conclusion_scope,
    }
)
graph = build_research_graph(deps, task_type=plan.task_type, checkpointer=checkpointer)
```

Do not recalculate `task_type` from Planner or Review output.

- [ ] **Step 6: Make Planner task-scoped**

Replace the fixed three-branch `planner_tasks` body with:

```python
enabled = [
    *state.get("required_nodes", []),
    *state.get("support_nodes", []),
    *state.get("optional_nodes", []),
]
missing_inputs = [name for name in state["required_inputs"] if not state.get(name)]
if missing_inputs:
    raise ValueError(f"Missing required task inputs: {', '.join(missing_inputs)}")
retry_tasks = [
    task
    for task in state.get("review_result", {}).get("retry_tasks", [])
    if task.get("node") in enabled
]
return {
    "run_id": state.get("run_id") or str(uuid4()),
    "as_of_date": state.get("as_of_date"),
    "investment_horizon": state.get("investment_horizon", "medium"),
    "retry_count": int(state.get("retry_count", 0)),
    "max_retries": int(state.get("max_retries", 2)),
    "planner_tasks": {
        "task_type": state["task_type"],
        "enabled_nodes": [name for name in enabled if name not in {"planner", "review", "report"}],
        "retry_tasks": retry_tasks,
        "conclusion_scope": state["conclusion_scope"],
    },
}
```

The service resolves any metadata-derived value, such as `industry_name` for `full`, before `run_research`; Planner treats a missing value at this point as a validation error. Retry tasks outside the enabled plan are discarded before Planner emits its work list.

- [ ] **Step 7: Record completed and failed nodes through the existing instrumentation seam**

On success, merge `{"completed_nodes": [name]}` into the node output. On exception, use this exact failure audit before re-raising:

```python
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
```

A fatal graph invocation does not return a final State, so its failed-node summary is read from the event/repository audit. Do not emit events for nodes absent from `plan.enabled_nodes`.

- [ ] **Step 8: Run routing and graph tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_routing.py tests/test_graph.py -q --basetemp .pytest-tmp/task2-green
```

Expected: all routing and graph tests pass; full mode still has 23 application nodes.

- [ ] **Step 9: Commit plan-driven graph assembly**

```powershell
git add src/diagram_langgraph_pipeline/state.py src/diagram_langgraph_pipeline/graph.py src/diagram_langgraph_pipeline/runner.py src/diagram_langgraph_pipeline/agents/planner_agent.py tests/test_graph.py
git commit -m "feat: build task-scoped research graphs"
```

---

### Task 3: Optional Marginal-Change Skip Semantics

**Files:**
- Modify: `src/diagram_langgraph_pipeline/agents/marginal_change_agent.py:11-42`
- Modify: `src/diagram_langgraph_pipeline/graph.py:131-184`
- Create: `tests/test_optional_nodes.py`

**Interfaces:**
- Consumes: `optional_node_statuses` State reducer from Task 2.
- Produces: `marginal_change_result.status` equal to `completed` or `skipped`.
- Produces: `optional_node_statuses["marginal_change"]` with `status` and `reason`.

- [ ] **Step 1: Write failing optional-node behavior tests**

```python
# tests/test_optional_nodes.py
import pytest

from diagram_langgraph_pipeline.agents import marginal_change_agent
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}))


def test_marginal_change_without_trustworthy_events_is_skipped():
    result = marginal_change_agent.run(
        {
            "as_of_date": "2026-08-05",
            "research_inputs": {"marginal_change": {"events": []}},
        },
        DEPS,
    )
    assert result["marginal_change_result"]["status"] == "skipped"
    assert result["optional_node_statuses"]["marginal_change"]["status"] == "skipped"
    assert result["optional_node_statuses"]["marginal_change"]["reason"]


def test_marginal_change_provider_failure_is_a_structured_skip(monkeypatch):
    monkeypatch.setattr(
        marginal_change_agent,
        "topic",
        lambda *args, **kwargs: {
            "events": [],
            "source_errors": ["provider unavailable"],
            "source_warnings": [],
        },
    )
    result = marginal_change_agent.run({"as_of_date": "2026-08-05"}, DEPS)
    status = result["optional_node_statuses"]["marginal_change"]
    assert status == {"status": "skipped", "reason": "provider unavailable"}


def test_marginal_change_programming_error_is_not_swallowed(monkeypatch):
    def broken_topic(*args, **kwargs):
        raise TypeError("contract bug")

    monkeypatch.setattr(marginal_change_agent, "topic", broken_topic)
    with pytest.raises(TypeError, match="contract bug"):
        marginal_change_agent.run({"as_of_date": "2026-08-05"}, DEPS)
```

- [ ] **Step 2: Run tests and verify the missing status failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_optional_nodes.py -q --basetemp .pytest-tmp/task3-red
```

Expected: first test fails because the node does not return `status` or `optional_node_statuses`; second test already passes and protects error propagation.

- [ ] **Step 3: Return a structured skip only for empty/untrusted data**

After filtering events, calculate:

```python
source_errors = list(payload.get("source_errors", []))
source_warnings = list(payload.get("source_warnings", []))
status = "completed" if events else "skipped"
reason = None
if not events:
    reason = (
        source_errors[0]
        if source_errors
        else source_warnings[0]
        if source_warnings
        else "没有带有效发布日期且不晚于分析截止日的可信边际变化事件"
    )
```

Return both:

```python
"marginal_change_result": {
    "status": status,
    "skip_reason": reason,
    # retain direction/events/excluded_events/coverage/evidence fields
},
"optional_node_statuses": {
    "marginal_change": {"status": status, "reason": reason}
},
```

Do not add a broad `except Exception`; `topic()` errors must propagate.

- [ ] **Step 4: Emit degraded status and suppress LLM work for skipped optional nodes**

In `_instrument`, read the current node's optional status after `function()` returns:

```python
optional_status = output.get("optional_node_statuses", {}).get(name, {})
skipped = optional_status.get("status") == "skipped"
runtime_status = "degraded" if skipped else "completed"
if not skipped:
    advisory = llm_orchestrator.analyze(name, state, output)
```

Persist and emit `runtime_status`; include the skip reason in event metadata. A skipped optional node still contributes its name to `completed_nodes` because its attempted execution finished, but its business result remains explicitly `skipped`.

- [ ] **Step 5: Run optional-node and full decision tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_optional_nodes.py tests/test_decision_and_review.py -q --basetemp .pytest-tmp/task3-green
```

Expected: all tests pass; unexpected errors still propagate.

- [ ] **Step 6: Commit optional skip behavior**

```powershell
git add src/diagram_langgraph_pipeline/agents/marginal_change_agent.py src/diagram_langgraph_pipeline/graph.py tests/test_optional_nodes.py
git commit -m "feat: degrade unavailable marginal change data"
```

---

### Task 4: Task-Scoped Join, Review, Decision Authority, and Report

**Files:**
- Modify: `src/diagram_langgraph_pipeline/agents/research_join_agent.py:10-73`
- Modify: `src/diagram_langgraph_pipeline/agents/review_agent.py:10-79`
- Modify: `src/diagram_langgraph_pipeline/agents/report_agent.py:11-84`
- Modify: `tests/test_decision_and_review.py`
- Create: `tests/test_task_scoped_report.py`

**Interfaces:**
- Consumes: `task_type`, `required_outputs`, `result_keys`, node-role lists, and `conclusion_scope` from State.
- Produces: `joined_research_result` containing only selected result keys.
- Produces: Review that distinguishes `skipped` from missing/failed.
- Produces: report section `任务执行范围` and only task-relevant business sections.

- [ ] **Step 1: Add failing task-scoped Review tests**

```python
# append to tests/test_decision_and_review.py
def test_technical_review_does_not_require_industry_or_fundamental_results():
    state = {
        "task_type": "technical",
        "required_outputs": ["stock_market_data_analysis", "stock_technical_result"],
        "stock_market_data_analysis": {"data_coverage": {"coverage_ratio": 1.0}},
        "stock_technical_result": {"trend": "up", "missing_items": []},
        "evidence_refs": [{}, {}, {}],
        "retry_count": 0,
        "max_retries": 1,
    }
    result = review_agent.run(state, DEPS)["review_result"]
    assert result["needs_retry"] is False
    assert "缺少行业价值测算" not in result["missing_items"]


def test_skipped_optional_marginal_change_does_not_trigger_retry():
    state = {
        "task_type": "fundamental",
        "required_outputs": ["business_result", "profit_forecast_result", "company_valuation_result"],
        "business_result": {"evidence": [{}]},
        "profit_forecast_result": {"evidence": [{}]},
        "company_valuation_result": {"evidence": [{}]},
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
```

- [ ] **Step 2: Add failing report-scope tests**

```python
# tests/test_task_scoped_report.py
from diagram_langgraph_pipeline.agents import report_agent
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}), llm=None)


def test_technical_report_discloses_scope_and_omits_fundamental_sections():
    state = {
        "run_id": "run-1",
        "task_type": "technical",
        "ticker": "AAPL",
        "company_name": "Apple",
        "as_of_date": "2026-08-05",
        "investment_horizon": "short",
        "required_nodes": ["stock_data_analysis", "stock_technical"],
        "support_nodes": ["planner", "stock_entry", "stock_data_fetch", "research_join", "review", "report"],
        "optional_nodes": [],
        "skipped_nodes": ["business", "profit_forecast", "company_valuation", "decision"],
        "completed_nodes": ["stock_data_analysis", "stock_technical"],
        "failed_nodes": [],
        "conclusion_scope": "仅技术面",
        "stock_technical_result": {"trend": "up"},
        "review_result": {"passed": True},
        "evidence_refs": [],
        "missing_items": [],
    }
    markdown = report_agent.run(state, DEPS)["final_markdown"]
    assert "任务执行范围" in markdown
    assert "仅技术面" in markdown
    assert "个股技术形态分析" in markdown
    assert "盈利预测与估值测算" not in markdown
    assert "综合买卖点判断" not in markdown
```

- [ ] **Step 3: Run focused tests and verify fixed full-scope behavior fails**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_decision_and_review.py tests/test_task_scoped_report.py -q --basetemp .pytest-tmp/task4-red
```

Expected: partial Review reports full-mode missing items and partial report renders all 15 sections.

- [ ] **Step 4: Make Research Join consume State result keys**

Replace the fixed `RESULT_KEYS` iteration with:

```python
result_keys = tuple(state.get("result_keys", ()))
selected_results = {key: state.get(key, {}) for key in result_keys}
for result in selected_results.values():
    evidence.extend(result.get("evidence", []))
    research_missing.extend(result.get("missing_items", []))
    research_missing.extend(result.get("coverage", {}).get("missing_items", []))
```

Set `joined_research_result` to include `task_type`, `conclusion_scope`, and `selected_results`. Do not add absent non-selected keys to `missing_items`.

- [ ] **Step 5: Make Review validate only required outputs**

Build missing results from State:

```python
required_outputs = tuple(state.get("required_outputs", ()))
missing = list(state.get("missing_items", []))
for key in required_outputs:
    if not state.get(key):
        missing.append(f"缺少必需结果：{key}")
```

Use task-specific coverage rules:

- `full`: retain current market coverage >= 0.8, industry coverage >= 0.6, evidence score >= 0.5.
- `industry`: industry coverage >= 0.6 and evidence score >= 0.5.
- `fundamental`: all required outputs exist and evidence score >= 0.5; skipped marginal change is informational.
- `technical`: market coverage >= 0.8 and both required outputs exist.
- `market`: index, sector, and sentiment results exist and evidence score >= 0.5.

Filter generated retry tasks to required outputs and actual data gaps. Never create a retry task for a node in `skipped_nodes` or an optional node with `status == "skipped"`.

- [ ] **Step 6: Render task-specific report sections**

Add an execution-scope section first:

```python
scope_section = _section(
    "任务执行范围",
    {
        "task_type": state.get("task_type", "full"),
        "required_nodes": state.get("required_nodes", []),
        "support_nodes": state.get("support_nodes", []),
        "optional_nodes": state.get("optional_nodes", []),
        "skipped_nodes": state.get("skipped_nodes", []),
        "completed_nodes": state.get("completed_nodes", []),
        "failed_nodes": state.get("failed_nodes", []),
        "optional_node_statuses": state.get("optional_node_statuses", {}),
        "conclusion_scope": state.get("conclusion_scope", "完整综合研究"),
    },
)
```

Define a `SECTION_BUILDERS` mapping keyed by task type. `full` retains all existing sections. `industry`, `fundamental`, `technical`, and `market` render only their business sections plus risks, evidence gaps, and Review. Only `full` includes “综合买卖点判断”. Partial reports must use a task-specific conclusion title and must not copy `decision_result` into the conclusion.

- [ ] **Step 7: Run scoped tests and full report regression**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_decision_and_review.py tests/test_task_scoped_report.py tests/test_full_node_pipeline.py -q --basetemp .pytest-tmp/task4-green
```

Expected: all focused tests pass; the full report still contains the existing full sections.

- [ ] **Step 8: Commit scoped synthesis and reporting**

```powershell
git add src/diagram_langgraph_pipeline/agents/research_join_agent.py src/diagram_langgraph_pipeline/agents/review_agent.py src/diagram_langgraph_pipeline/agents/report_agent.py tests/test_decision_and_review.py tests/test_task_scoped_report.py
git commit -m "feat: scope review and reports by task"
```

---

### Task 5: Task-Aware Service and CLI Experience

**Files:**
- Modify: `src/diagram_langgraph_pipeline/service.py:42-213`
- Modify: `src/diagram_langgraph_pipeline/cli.py:86-285`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `TaskType`, `TaskExecutionPlan`, and `get_execution_plan()`.
- Produces: `RunOptions.task_type: TaskType` and `RunOptions.industry_name: str | None`.
- Produces CLI: `run [TICKER] --task <type> --industry-name <name>`.
- Produces result summary keys: `task_type`, `enabled_nodes`, `skipped_nodes`, `completed_nodes`, `failed_nodes`, and `conclusion_scope`.

- [ ] **Step 1: Write failing CLI option and validation tests**

```python
# append to tests/test_cli.py
from diagram_langgraph_pipeline.routing import TaskType
from diagram_langgraph_pipeline.service import RunOptions, validate_options


def test_run_accepts_explicit_task(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(cli, "load_settings", lambda: {})
    monkeypatch.setattr(cli, "paid_provider_names", lambda settings: [])

    def fake_run(options, settings, event_callback=None):
        captured["options"] = options
        return {}, {
            "run_id": "run-1", "ticker": "AAPL", "task_type": "technical",
            "coverage": {}, "provider_calls": {}, "d4f_token_usage": {},
            "decision": {}, "review": {}, "report_path": str(tmp_path / "report.md"),
            "enabled_nodes": [], "skipped_nodes": [], "completed_nodes": [],
            "failed_nodes": [], "conclusion_scope": "仅技术面",
        }

    monkeypatch.setattr(cli, "run_analysis", fake_run)
    result = runner.invoke(cli.app, ["run", "AAPL", "--task", "technical", "--json", "--no-llm"])
    assert result.exit_code == 0
    assert captured["options"].task_type is TaskType.TECHNICAL


def test_market_task_does_not_require_ticker():
    validate_options(RunOptions(ticker=None, task_type=TaskType.MARKET))


def test_industry_task_requires_industry_name():
    with pytest.raises(Exception, match="行业名称"):
        validate_options(RunOptions(ticker=None, task_type=TaskType.INDUSTRY))
```

- [ ] **Step 2: Run CLI tests and verify missing interfaces**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cli.py -q --basetemp .pytest-tmp/task5-red
```

Expected: FAIL because `--task`, optional ticker, and task-aware `RunOptions` do not exist.

- [ ] **Step 3: Extend RunOptions and validate inputs by plan**

Use:

```python
@dataclass(frozen=True)
class RunOptions:
    ticker: str | None = None
    task_type: TaskType = TaskType.FULL
    industry_name: str | None = None
    report_days: int = 70
    technical_days: int = 251
    as_of: date = field(default_factory=date.today)
    benchmark: str | None = None
    sector_index: str | None = None
    horizon: str = "medium"
    llm: bool | None = None
    offline: bool = False
    refresh: bool = False
    allow_paid: bool = False
    output: Path | None = None
```

`validate_options` must call `get_execution_plan(options.task_type)` and enforce:

- `full`, `fundamental`, `technical`: non-empty ticker.
- `industry`: non-empty industry name.
- `market`: no ticker requirement.
- existing date-window, horizon, and offline/refresh checks remain.

- [ ] **Step 4: Make service preparation task-aware**

Resolve the plan first. Only load security metadata and prefetch a target ticker when the plan enables `stock_data_fetch`. For `industry`, use the explicit industry name and do not call target-market providers. For `market`, prepare benchmark/sector identifiers without inventing a target company. Build the State with `task_type=plan.task_type.value` and pass it to `run_research`.

Use an empty preview payload for runs without `stock_data_fetch`:

```python
preview = {"bars": [], "minute_bars": [], "valuations": [], "metadata": {}}
research_start = options.as_of.isoformat()
```

Only apply the existing “target ticker has no bars” error to plans that enable `stock_data_fetch`.

- [ ] **Step 5: Add `--task` and conditional command inputs**

Change the command parameters to:

```python
ticker: Optional[str] = typer.Argument(None, help="需要个股数据的任务填写证券代码。")
task: TaskType = typer.Option(TaskType.FULL, "--task", case_sensitive=False)
industry_name: Optional[str] = typer.Option(None, "--industry-name")
```

Construct `RunOptions` with keyword arguments, not positional arguments. Keep the default task `full`.

- [ ] **Step 6: Add plan preview and progress display**

Before starting a non-JSON run, render a Rich table with task name, conclusion scope, required/support/optional node counts, and skipped-node count. Implement a small callable progress printer that receives a plan, counts terminal node events, and prints `completed/total`, current stage, and degraded reason. JSON mode uses `_quiet_event_printer` and keeps stdout clean.

Required display assertions:

```python
def test_plan_preview_lists_scope_and_skipped_count(monkeypatch):
    messages = []
    monkeypatch.setattr(cli, "stdout", type("Console", (), {"print": lambda self, value: messages.append(str(value))})())
    cli._print_task_plan(get_execution_plan("technical"))
    rendered = "\n".join(messages)
    assert "technical" in rendered
    assert "仅技术面" in rendered
```

- [ ] **Step 7: Make the wizard ask task first and only request relevant fields**

Prompt task with the five Chinese labels. Then:

- Ask ticker for `full`, `fundamental`, `technical`.
- Ask industry name for `industry`; for `full`, allow metadata resolution and an optional override.
- Ask benchmark/sector for `market` and `full`.
- Ask technical window only when `stock_data_fetch`, `index_analysis`, or `sector_technical` is enabled.
- Show the plan preview and require confirmation before calling `run_analysis`.

- [ ] **Step 8: Extend stable JSON/result summary fields**

Add to `result_summary`:

```python
"task_type": state.get("task_type", "full"),
"enabled_nodes": [
    *state.get("required_nodes", []),
    *state.get("support_nodes", []),
    *state.get("optional_nodes", []),
],
"skipped_nodes": state.get("skipped_nodes", []),
"completed_nodes": state.get("completed_nodes", []),
"failed_nodes": state.get("failed_nodes", []),
"conclusion_scope": state.get("conclusion_scope"),
```

Partial tasks may return an empty `decision` object; `_print_summary` must display a task-specific conclusion instead of `decision=unknown`.

- [ ] **Step 9: Run service and CLI tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_graph.py tests/test_routing.py -q --basetemp .pytest-tmp/task5-green
```

Expected: all tests pass; `run --help` lists `--task` and `--industry-name`.

- [ ] **Step 10: Commit service and CLI routing**

```powershell
git add src/diagram_langgraph_pipeline/service.py src/diagram_langgraph_pipeline/cli.py tests/test_cli.py
git commit -m "feat: expose task routing in cli"
```

---

### Task 6: Five-Mode End-to-End Verification and Documentation

**Files:**
- Create: `tests/test_task_router_pipeline.py`
- Modify: `README.md:25-66`

**Interfaces:**
- Consumes: all Router, graph, agent, service, and CLI interfaces from Tasks 1-5.
- Produces: executable acceptance coverage for all five task modes.

- [ ] **Step 1: Write parameterized end-to-end acceptance tests**

Use deterministic demo data and a recording fake Provider/LLM. For each task, call `run_research` with `task_type` and assert:

```python
@pytest.mark.parametrize(
    ("task_type", "must_complete", "must_skip", "has_decision"),
    [
        ("full", "industry_valuation", None, True),
        ("industry", "industry_valuation", "stock_data_fetch", False),
        ("fundamental", "company_valuation", "stock_technical", False),
        ("technical", "stock_technical", "industry_report", False),
        ("market", "sentiment", "business", False),
    ],
)
def test_task_pipeline_executes_only_selected_scope(
    task_type, must_complete, must_skip, has_decision, deterministic_dependencies
):
    result = run_research(make_state(task_type), deterministic_dependencies)
    assert must_complete in result["completed_nodes"]
    if must_skip:
        assert must_skip in result["skipped_nodes"]
        assert must_skip not in result["completed_nodes"]
    assert bool(result.get("decision_result")) is has_decision
    assert result["task_type"] == task_type
    assert "任务执行范围" in result["final_markdown"]
```

The fake dependencies must record Provider and LLM calls. Add assertions that no skipped node appears in node events and that a technical run never requests industry/policy/company research datasets.

- [ ] **Step 2: Run acceptance tests and fix only integration defects**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_task_router_pipeline.py -q --basetemp .pytest-tmp/task6-router
```

Expected: five task cases pass. If a case fails, correct the owning module from Tasks 1-5 without broad refactoring.

- [ ] **Step 3: Update README task-mode documentation**

Add a “任务 Router” section with these exact examples:

```powershell
diagram-langgraph-pipeline run AAPL --task full --no-llm
diagram-langgraph-pipeline run --task industry --industry-name 通信 --no-llm
diagram-langgraph-pipeline run AAPL --task fundamental --no-llm
diagram-langgraph-pipeline run AAPL --task technical --no-llm
diagram-langgraph-pipeline run --task market --benchmark ^GSPC --sector-index XLK --no-llm
```

Explain that omitted `--task` defaults to `full`, partial tasks do not emit complete investment advice, marginal-change data may degrade to skipped, and disabled nodes make no Provider/LLM calls.

- [ ] **Step 4: Run the full test suite**

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp/full-suite
```

Expected: all existing 52 tests plus the new Router tests pass with zero failures or errors.

- [ ] **Step 5: Run both CLI entry-point smoke tests**

```powershell
.venv\Scripts\python.exe -m diagram_langgraph_pipeline --help
.venv\Scripts\diagram-langgraph-pipeline.exe run --help
```

Expected: both exit 0; `run --help` shows all five task values.

- [ ] **Step 6: Run offline deterministic smoke tests for all task types**

Extend `demo` with a `--task` option or invoke the deterministic test helper directly. Run each task once without network, PostgreSQL, paid Providers, or LLM. Expected: every mode reaches report generation; only `full` contains the comprehensive decision section.

- [ ] **Step 7: Clean test artifacts and inspect repository scope**

Resolve the exact `.pytest-tmp` path, verify it is inside the repository, then remove only that directory. Run:

```powershell
git status --short
git diff --check
```

Expected: only intended Router, CLI, tests, README, and plan/spec files are changed; no `.venv`, outputs, credentials, reports, database data, or temporary files are tracked.

- [ ] **Step 8: Commit acceptance tests and documentation**

```powershell
git add tests/test_task_router_pipeline.py README.md
git commit -m "test: verify task router workflows"
```

---

## Final Verification Gate

- [ ] Confirm the full test command reports zero failures and zero errors.
- [ ] Confirm both CLI entry points exit 0.
- [ ] Confirm all five task plans reach `report` in deterministic offline runs.
- [ ] Confirm only `full` contains `decision` and a comprehensive buy/hold/watch/reduce/sell conclusion.
- [ ] Confirm a missing marginal-change source emits `degraded/skipped`, does not call the LLM for that node, and does not block company valuation.
- [ ] Confirm a forced `TypeError` inside marginal-change processing fails rather than being skipped.
- [ ] Confirm no skipped node appears in node-run events, Provider calls, or LLM calls.
- [ ] Confirm JSON stdout contains one document and progress remains on stderr.
- [ ] Confirm `git diff --check` is clean and no secrets or local database settings are tracked.
