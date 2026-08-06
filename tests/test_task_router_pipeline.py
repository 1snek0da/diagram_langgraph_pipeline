from __future__ import annotations

from threading import Lock

import pytest

pytest.importorskip("langgraph")

from diagram_langgraph_pipeline.contracts import LLMResponse, SourceRequest
from diagram_langgraph_pipeline.demo_data import demo_research_inputs, make_market_payload
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.events import RecordingEventSink
from diagram_langgraph_pipeline.providers import (
    InMemoryMarketDataProvider,
    InputResearchProvider,
)
from diagram_langgraph_pipeline.routing import get_execution_plan
from diagram_langgraph_pipeline.runner import run_research


class RecordingMarketDataProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = Lock()
        self._provider = InMemoryMarketDataProvider(
            {
                "STOCK": make_market_payload(20.0, 0.0010),
                "BENCH": make_market_payload(100.0, 0.0003),
                "SECTOR": make_market_payload(50.0, 0.0006),
            }
        )

    def fetch(self, ticker, start_date, end_date):
        with self._lock:
            self.calls.append(ticker)
        return self._provider.fetch(ticker, start_date, end_date)


class RecordingResearchProvider:
    name = "recording-input"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = Lock()
        self._provider = InputResearchProvider()

    def fetch(self, request: SourceRequest):
        with self._lock:
            self.calls.append(request.topic or "")
        return self._provider.fetch(request)


class RecordingLLM:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self._lock = Lock()

    def generate(self, messages, *, max_tokens=None, temperature=None):
        with self._lock:
            self.calls.append(messages)
        return LLMResponse(text="offline", model="fake", provider="test")


def make_state(task_type: str) -> dict:
    return {
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
        "task_type": task_type,
    }


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
    task_type, must_complete, must_skip, has_decision
):
    market_data = RecordingMarketDataProvider()
    research = RecordingResearchProvider()
    llm = RecordingLLM()
    events = RecordingEventSink()
    deps = AgentDependencies(
        market_data=market_data,
        research=research,
        llm=llm,
        events=events,
    )

    result = run_research(make_state(task_type), deps)
    plan = get_execution_plan(task_type)
    event_nodes = {
        event.stage for event in events.snapshot() if event.event_type == "node"
    }

    assert result["ticker"] == "STOCK"
    assert result["task_type"] == task_type
    assert must_complete in result["completed_nodes"]
    if must_skip:
        assert must_skip in result["skipped_nodes"]
        assert must_skip not in result["completed_nodes"]
    assert bool(result.get("decision_result")) is has_decision
    assert "任务执行范围" in result["final_markdown"]
    assert event_nodes == set(plan.enabled_nodes)
    assert event_nodes.isdisjoint(plan.skipped_nodes)
    assert len(llm.calls) == (1 if task_type == "full" else 0)

    if task_type == "technical":
        assert research.calls == []
        assert set(market_data.calls) == {"STOCK"}


def test_each_task_uses_only_its_selected_provider_scope():
    expected_research_topics = {
        "full": {
            "industry_report",
            "upstream_capex",
            "policy",
            "industry_valuation",
            "business",
            "profit_forecast",
            "marginal_change",
            "company_valuation",
            "sentiment",
        },
        "industry": {
            "industry_report",
            "upstream_capex",
            "policy",
            "industry_valuation",
        },
        "fundamental": {
            "business",
            "profit_forecast",
            "marginal_change",
            "company_valuation",
        },
        "technical": set(),
        "market": {"sentiment"},
    }
    expected_market_tickers = {
        "full": {"STOCK", "BENCH", "SECTOR"},
        "industry": set(),
        "fundamental": {"STOCK"},
        "technical": {"STOCK"},
        "market": {"BENCH", "SECTOR"},
    }

    for task_type in expected_research_topics:
        market_data = RecordingMarketDataProvider()
        research = RecordingResearchProvider()
        result = run_research(
            make_state(task_type),
            AgentDependencies(market_data=market_data, research=research, llm=None),
        )

        assert result["final_markdown"]
        assert set(research.calls) == expected_research_topics[task_type]
        assert set(market_data.calls) == expected_market_tickers[task_type]


def test_only_full_report_contains_comprehensive_decision_section():
    reports = {}
    for task_type in ("full", "industry", "fundamental", "technical", "market"):
        reports[task_type] = run_research(
            make_state(task_type),
            AgentDependencies(
                market_data=RecordingMarketDataProvider(),
                research=RecordingResearchProvider(),
                llm=None,
            ),
        )["final_markdown"]

    assert "综合买卖点判断" in reports["full"]
    assert all(
        "综合买卖点判断" not in reports[task_type]
        for task_type in ("industry", "fundamental", "technical", "market")
    )
