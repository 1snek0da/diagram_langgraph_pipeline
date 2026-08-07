import httpx
import pytest

from diagram_langgraph_pipeline.routing import TaskType
from diagram_langgraph_pipeline.ui.api_gateway import (
    ApiAnalysisGateway,
    GatewayRequestError,
    create_gateway,
)
from diagram_langgraph_pipeline.ui.models import AnalysisRequest


def test_gateway_maps_task_catalog_and_create_request():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/v1/task-types":
            return httpx.Response(
                200,
                json=[
                    {
                        "task_type": "technical",
                        "display_name": "技术分析",
                        "description": "技术指标",
                        "required_nodes": ["stock_technical"],
                        "support_nodes": ["planner"],
                        "optional_nodes": [],
                        "skipped_nodes": ["industry_report"],
                        "required_inputs": ["ticker", "as_of_date"],
                        "conclusion_scope": "仅技术面",
                        "paid_sources_available": False,
                    }
                ],
            )
        return httpx.Response(
            202,
            json={
                "run_id": "00000000-0000-0000-0000-000000000001",
                "status": "pending",
                "poll_url": "/api/v1/analysis-runs/00000000-0000-0000-0000-000000000001",
            },
        )

    client = httpx.Client(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    gateway = ApiAnalysisGateway("http://test", client=client)

    tasks = gateway.task_types()
    run_id = gateway.create_run(
        AnalysisRequest(ticker="aapl", task_type=TaskType.TECHNICAL)
    )

    assert tasks[0].task_type is TaskType.TECHNICAL
    assert run_id == "00000000-0000-0000-0000-000000000001"
    assert requests[-1].method == "POST"
    assert b'"ticker":"AAPL"' in requests[-1].content


def test_gateway_never_maps_report_path_from_server_payload():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "run_id": "00000000-0000-0000-0000-000000000001",
                "ticker": "AAPL",
                "task_type": "technical",
                "status": "completed",
                "created_at": "2026-08-06T00:00:00Z",
                "updated_at": "2026-08-06T00:01:00Z",
                "report_path": "C:/secret/report.md",
            },
        )
    )
    client = httpx.Client(base_url="http://test", transport=transport)
    gateway = ApiAnalysisGateway("http://test", client=client)

    run = gateway.get_run("run-1")

    assert not hasattr(run, "report_path")


def test_gateway_maps_safe_api_error_without_leaking_unknown_payload():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            503,
            json={
                "error": {
                    "code": "STORAGE_UNAVAILABLE",
                    "message": "Storage service unavailable",
                    "retryable": True,
                },
                "debug": "secret-value",
            },
        )
    )
    gateway = ApiAnalysisGateway(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=transport),
    )

    with pytest.raises(GatewayRequestError) as caught:
        gateway.get_run("run-1")

    assert caught.value.code == "STORAGE_UNAVAILABLE"
    assert caught.value.retryable is True
    assert "secret-value" not in str(caught.value)


def test_create_gateway_is_always_http_backed():
    gateway = create_gateway({"DLP_API_BASE_URL": "http://example.test/"})

    assert isinstance(gateway, ApiAnalysisGateway)
    assert gateway.base_url == "http://example.test"

