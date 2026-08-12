from fastapi.testclient import TestClient
from pathlib import Path

from diagram_langgraph_pipeline.api.app import create_app


class LifecycleJobs:
    def __init__(self):
        self.recover_calls = 0
        self.shutdown_calls = 0

    def recover(self):
        self.recover_calls += 1
        return 0

    def shutdown(self):
        self.shutdown_calls += 1


class HealthRepository:
    def __init__(self, error=None):
        self.error = error

    def check_health(self):
        if self.error:
            raise self.error
        return {"ok": True, "database": "research", "host": "secret-host"}


def test_health_reports_service_and_storage_without_database_details():
    app = create_app(repository=HealthRepository(), job_service=LifecycleJobs())

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"service": "ok", "storage": "ok"}


def test_lifespan_recovers_and_shuts_down_jobs():
    jobs = LifecycleJobs()
    app = create_app(repository=HealthRepository(), job_service=jobs)

    with TestClient(app):
        assert jobs.recover_calls == 1

    assert jobs.shutdown_calls == 1


def test_storage_failure_uses_safe_503_envelope():
    app = create_app(
        repository=HealthRepository(RuntimeError("postgresql://user:secret@host/db")),
        job_service=LifecycleJobs(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "STORAGE_UNAVAILABLE",
            "message": "Storage service unavailable",
            "retryable": True,
        }
    }
    assert "secret" not in response.text


def test_frontend_root_and_client_routes_are_served_without_hijacking_api(tmp_path):
    (tmp_path / "index.html").write_text("<html>sites-v2</html>", encoding="utf-8")
    app = create_app(
        repository=HealthRepository(),
        job_service=LifecycleJobs(),
        frontend_dist=tmp_path,
    )

    with TestClient(app) as client:
        root = client.get("/")
        route = client.get("/report?run_id=run-1")
        api = client.get("/api/v1/health")

    assert root.status_code == 200
    assert root.text == "<html>sites-v2</html>"
    assert route.status_code == 200
    assert route.text == "<html>sites-v2</html>"
    assert api.json() == {"service": "ok", "storage": "ok"}


def test_vinext_client_layout_uses_the_published_terminal_as_entry(tmp_path):
    client_dir = tmp_path / "client"
    client_dir.mkdir()
    (client_dir / "trading-analysis-ui-design.html").write_text(
        "<html>sites-v2-client</html>", encoding="utf-8"
    )
    app = create_app(
        repository=HealthRepository(),
        job_service=LifecycleJobs(),
        frontend_dist=tmp_path,
    )

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text == "<html>sites-v2-client</html>"
