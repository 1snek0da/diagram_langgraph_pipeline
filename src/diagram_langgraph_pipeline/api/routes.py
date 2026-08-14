"""Versioned HTTP routes backed by the repository and job service seams."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Mapping, TypeVar

from fastapi import APIRouter, Query, status

from ..routing import ALL_NODE_NAMES, TaskType, get_execution_plan
from ..runtime_config import paid_provider_names
from .catalog import task_catalog
from .errors import ApiError
from .schemas import (
    AcceptedRunResponse,
    CreateAnalysisRunRequest,
    MarketBarsResponse,
    NodeListResponse,
    NodeResponse,
    ReportResponse,
    RunListResponse,
    RunResponse,
    RunStatus,
    TaskTypeResponse,
)


T = TypeVar("T")


def _storage_call(function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return function(*args, **kwargs)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(
            503,
            "STORAGE_UNAVAILABLE",
            "Storage service unavailable",
            retryable=True,
        ) from exc


def _run_response(record: Mapping[str, Any]) -> RunResponse:
    values = dict(record)
    values["run_id"] = str(values.pop("id", values.get("run_id")))
    return RunResponse.model_validate(values)


def _require_run(repository: Any, run_id: str) -> dict[str, Any]:
    record = _storage_call(repository.get_run_record, run_id)
    if not record:
        raise ApiError(404, "RUN_NOT_FOUND", "Analysis run not found")
    return record


def create_router(repository: Any, jobs: Any, settings: Mapping[str, str]) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    def health() -> dict[str, str]:
        _storage_call(repository.check_health)
        return {"service": "ok", "storage": "ok"}

    @router.get("/task-types", response_model=list[TaskTypeResponse])
    def task_types() -> list[TaskTypeResponse]:
        return task_catalog(
            paid_sources_available=bool(paid_provider_names(settings))
        )

    @router.post(
        "/analysis-runs",
        response_model=AcceptedRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_run(request: CreateAnalysisRunRequest) -> AcceptedRunResponse:
        run_id = jobs.submit(request)
        return AcceptedRunResponse(
            run_id=run_id,
            poll_url=f"/api/v1/analysis-runs/{run_id}",
        )

    @router.get("/analysis-runs", response_model=RunListResponse)
    def list_runs(
        ticker: str | None = None,
        task_type: TaskType | None = None,
        run_status: RunStatus | None = Query(default=None, alias="status"),
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> RunListResponse:
        records, total = _storage_call(
            repository.list_run_records,
            ticker=ticker,
            task_type=task_type.value if task_type else None,
            status=run_status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
        return RunListResponse(
            items=tuple(_run_response(record) for record in records),
            total=total,
            limit=limit,
            offset=offset,
        )

    @router.get("/analysis-runs/{run_id}", response_model=RunResponse)
    def get_run(run_id: str) -> RunResponse:
        return _run_response(_require_run(repository, run_id))

    @router.get(
        "/analysis-runs/{run_id}/nodes",
        response_model=NodeListResponse,
    )
    def get_nodes(run_id: str) -> NodeListResponse:
        run = _require_run(repository, run_id)
        plan = get_execution_plan(run["task_type"])
        actual_rows = _storage_call(repository.list_node_records, run_id)
        actual = {row["node_name"]: row for row in actual_rows}
        roles = {
            **{name: "required" for name in plan.required_nodes},
            **{name: "support" for name in plan.support_nodes},
            **{name: "optional" for name in plan.optional_nodes},
            **{name: "skipped" for name in plan.skipped_nodes},
        }
        items: list[NodeResponse] = []
        for name in ALL_NODE_NAMES:
            role = roles[name]
            row = actual.get(name, {})
            items.append(
                NodeResponse(
                    name=name,
                    role=role,
                    status=(
                        "skipped"
                        if role == "skipped"
                        else str(row.get("status") or "pending")
                    ),
                    attempt_no=row.get("attempt_no"),
                    started_at=row.get("started_at"),
                    ended_at=row.get("ended_at"),
                    error_summary=row.get("error_summary"),
                )
            )
        return NodeListResponse(items=tuple(items))

    @router.get(
        "/analysis-runs/{run_id}/report",
        response_model=ReportResponse,
    )
    def get_report(run_id: str) -> ReportResponse:
        run = _require_run(repository, run_id)
        report = _storage_call(repository.get_report_record, run_id)
        if not report:
            if run["status"] in {"pending", "running"}:
                raise ApiError(
                    409,
                    "REPORT_NOT_READY",
                    "Analysis report is not ready",
                    retryable=True,
                )
            raise ApiError(404, "REPORT_NOT_FOUND", "Analysis report not found")
        return ReportResponse.model_validate(report)

    @router.get("/market-bars", response_model=MarketBarsResponse)
    def get_market_bars(
        ticker: str = Query(min_length=1),
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MarketBarsResponse:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise ApiError(422, "VALIDATION_ERROR", "Invalid request")
        records = _storage_call(
            repository.get_market_bar_records,
            normalized_ticker,
            start_date,
            end_date,
        )
        return MarketBarsResponse(ticker=normalized_ticker, items=tuple(records))

    return router

