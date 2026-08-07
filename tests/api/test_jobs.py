from diagram_langgraph_pipeline.api.jobs import AnalysisJobService
from diagram_langgraph_pipeline.api.schemas import CreateAnalysisRunRequest


class ImmediateExecutor:
    def __init__(self):
        self.shutdown_args = None

    def submit(self, function, *args):
        function(*args)
        return object()

    def shutdown(self, wait=True, cancel_futures=False):
        self.shutdown_args = (wait, cancel_futures)


class FakeApiRepository:
    def __init__(self):
        self.created_run_id = None
        self.created_request = None
        self.statuses = []
        self.last_error_code = None
        self.last_error_summary = None
        self.recover_calls = 0

    def create_pending_run(self, run_id, request):
        self.created_run_id = run_id
        self.created_request = request

    def update_run_lifecycle(
        self, run_id, status, *, error_code=None, error_summary=None
    ):
        self.statuses.append(status)
        self.last_error_code = error_code
        self.last_error_summary = error_summary

    def interrupt_incomplete_runs(self):
        self.recover_calls += 1
        return 2


def make_service(repository, *, result=None, error=None, executor=None):
    def runner(options, settings, event_callback=None):
        if error is not None:
            raise error
        summary = result or {"optional_node_statuses": {}}
        return summary, summary

    return AnalysisJobService(
        repository=repository,
        settings={"DATABASE_URL": "postgresql://test"},
        runner=runner,
        executor=executor or ImmediateExecutor(),
    )


def test_submit_uses_one_run_id_for_database_and_runner():
    repository = FakeApiRepository()
    captured = {}

    def runner(options, settings, event_callback=None):
        captured["run_id"] = options.run_id
        return {"optional_node_statuses": {}}, {"optional_node_statuses": {}}

    service = AnalysisJobService(
        repository=repository,
        settings={"DATABASE_URL": "postgresql://test"},
        runner=runner,
        executor=ImmediateExecutor(),
    )

    run_id = service.submit(
        CreateAnalysisRunRequest(ticker="AAPL", task_type="technical")
    )

    assert str(run_id) == captured["run_id"] == repository.created_run_id
    assert repository.created_request["ticker"] == "AAPL"
    assert repository.created_request["task_type"] == "technical"
    assert repository.statuses == ["running", "completed"]


def test_optional_skip_finishes_as_degraded():
    repository = FakeApiRepository()
    service = make_service(
        repository,
        result={
            "optional_node_statuses": {
                "marginal_change": {"status": "skipped"}
            }
        },
    )

    service.submit(
        CreateAnalysisRunRequest(ticker="AAPL", task_type="fundamental")
    )

    assert repository.statuses[-1] == "degraded"


def test_runner_error_is_sanitized():
    repository = FakeApiRepository()
    service = make_service(repository, error=RuntimeError("secret-value"))

    service.submit(CreateAnalysisRunRequest(ticker="AAPL"))

    assert repository.last_error_code == "ANALYSIS_FAILED"
    assert repository.last_error_summary == "RuntimeError"
    assert "secret-value" not in repository.last_error_summary


def test_recover_delegates_to_repository():
    repository = FakeApiRepository()
    service = make_service(repository)

    assert service.recover() == 2
    assert repository.recover_calls == 1


def test_shutdown_delegates_to_executor():
    repository = FakeApiRepository()
    executor = ImmediateExecutor()
    service = make_service(repository, executor=executor)

    service.shutdown()

    assert executor.shutdown_args == (True, False)
