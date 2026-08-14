from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from diagram_langgraph_pipeline.api.app import create_app
from diagram_langgraph_pipeline.api.jobs import AnalysisJobService
from diagram_langgraph_pipeline.routing import TaskType


RUN_ID = "00000000-0000-0000-0000-000000000001"


class ImmediateExecutor:
    def submit(self, function, *args):
        function(*args)
        return object()

    def shutdown(self, wait=True, cancel_futures=False):
        return None


class DeterministicRepository:
    def __init__(self):
        self.request = None
        self.status = "pending"

    def create_pending_run(self, run_id, request):
        self.request = request

    def update_run_lifecycle(self, run_id, status, *, error_code=None, error_summary=None):
        self.status = status

    def interrupt_incomplete_runs(self):
        return 0

    def check_health(self):
        return {"ok": True}

    def get_run_record(self, run_id):
        if not self.request:
            return None
        now = datetime(2026, 8, 6, tzinfo=timezone.utc)
        return {
            "id": run_id,
            "ticker": self.request["ticker"],
            "industry_name": self.request.get("industry_name"),
            "as_of_date": self.request["as_of_date"],
            "investment_horizon": self.request["investment_horizon"],
            "task_type": self.request["task_type"],
            "user_request": None,
            "status": self.status,
            "retry_count": 0,
            "max_retries": 2,
            "error_code": None,
            "error_summary": None,
            "created_at": now,
            "updated_at": now,
        }

    def get_report_record(self, run_id):
        if self.status not in {"completed", "degraded"}:
            return None
        return {
            "run_id": run_id,
            "report_markdown": "# deterministic report",
            "created_at": datetime(2026, 8, 6, tzinfo=timezone.utc),
        }


def deterministic_web_app(task_type):
    repository = DeterministicRepository()

    def runner(options, settings, event_callback=None):
        return {
            "run_id": options.run_id,
            "optional_node_statuses": {},
        }, {"optional_node_statuses": {}}

    jobs = AnalysisJobService(
        repository,
        {"DATABASE_URL": "postgresql://test"},
        runner=runner,
        executor=ImmediateExecutor(),
    )
    return create_app(repository=repository, job_service=jobs, settings={}), repository


@pytest.mark.parametrize("task_type", list(TaskType))
def test_api_runs_every_router_mode_to_terminal_report(task_type):
    app, repository = deterministic_web_app(task_type)

    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/analysis-runs",
            json={
                "ticker": "AAPL",
                "task_type": task_type.value,
                "as_of_date": "2026-08-06",
                "investment_horizon": "medium",
                "offline": True,
            },
        )
        run_id = accepted.json()["run_id"]
        run = client.get(f"/api/v1/analysis-runs/{run_id}").json()
        report = client.get(f"/api/v1/analysis-runs/{run_id}/report")

    assert accepted.status_code == 202
    assert run["status"] in {"completed", "degraded"}
    assert report.status_code == 200
    assert repository.request["task_type"] == task_type.value
