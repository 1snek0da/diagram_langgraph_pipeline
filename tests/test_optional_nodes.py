import pytest
from pydantic import ValidationError

from diagram_langgraph_pipeline.agents import marginal_change_agent
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.events import RecordingEventSink
from diagram_langgraph_pipeline.graph import _instrument
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider
from diagram_langgraph_pipeline.schemas.research import MarginalChangeInput


DEPS = AgentDependencies(market_data=InMemoryMarketDataProvider({}))


class RecordingRepository:
    def __init__(self):
        self.node_runs = []

    def record_node_run(
        self,
        run_id,
        node_name,
        status,
        input_payload,
        output_payload,
        error_message=None,
    ):
        self.node_runs.append(
            {
                "run_id": run_id,
                "node_name": node_name,
                "status": status,
                "input_payload": input_payload,
                "output_payload": output_payload,
                "error_message": error_message,
            }
        )


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def analyze(self, name, state, output):
        self.calls.append((name, state, output))
        return None


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

    assert result["optional_node_statuses"]["marginal_change"] == {
        "status": "skipped",
        "reason": "provider unavailable",
    }


def test_marginal_change_programming_error_is_not_swallowed(monkeypatch):
    def broken_topic(*args, **kwargs):
        raise TypeError("contract bug")

    monkeypatch.setattr(marginal_change_agent, "topic", broken_topic)

    with pytest.raises(TypeError, match="contract bug"):
        marginal_change_agent.run({"as_of_date": "2026-08-05"}, DEPS)


def test_marginal_change_schema_error_is_not_swallowed(monkeypatch):
    def invalid_topic(*args, **kwargs):
        return MarginalChangeInput.model_validate(
            {"events": [{"event_type": "order"}]}
        ).model_dump(mode="python")

    monkeypatch.setattr(marginal_change_agent, "topic", invalid_topic)

    with pytest.raises(ValidationError):
        marginal_change_agent.run({"as_of_date": "2026-08-05"}, DEPS)


def test_instrumentation_records_skipped_optional_node_as_degraded_without_llm():
    repository = RecordingRepository()
    events = RecordingEventSink()
    deps = AgentDependencies(
        market_data=InMemoryMarketDataProvider({}),
        repository=repository,
        events=events,
    )
    orchestrator = RecordingOrchestrator()

    wrapped = _instrument(
        "marginal_change",
        lambda state, deps: {
            "marginal_change_result": {
                "status": "skipped",
                "skip_reason": "provider unavailable",
            },
            "optional_node_statuses": {
                "marginal_change": {
                    "status": "skipped",
                    "reason": "provider unavailable",
                }
            },
        },
        deps,
        orchestrator,
    )

    result = wrapped({"run_id": "optional-run", "llm_scope": "all_nodes"})

    assert result["completed_nodes"] == ["marginal_change"]
    assert orchestrator.calls == []
    assert repository.node_runs[-1]["status"] == "degraded"
    finished = events.snapshot()[-1]
    assert finished.status == "degraded"
    assert finished.metadata["reason"] == "provider unavailable"
