"""HTTP-only implementation of the Streamlit analysis gateway."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import httpx

from ..runtime_config import load_settings
from .models import (
    AnalysisRequest,
    AnalysisRun,
    MarketBar,
    MarketChart,
    NodeView,
    ReportView,
    RunPage,
    TaskTypeView,
)


class GatewayRequestError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ApiAnalysisGateway:
    def __init__(
        self,
        base_url: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self.base_url, timeout=15.0)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise GatewayRequestError(
                "NETWORK_ERROR", "无法连接分析服务", retryable=True
            ) from exc
        if response.is_success:
            return response.json()
        try:
            error = response.json().get("error", {})
        except (ValueError, AttributeError):
            error = {}
        code = str(error.get("code") or f"HTTP_{response.status_code}")
        message = str(error.get("message") or "分析服务请求失败")
        retryable = bool(
            error.get("retryable", response.status_code >= 500)
        )
        raise GatewayRequestError(code, message, retryable)

    def task_types(self) -> list[TaskTypeView]:
        payload = self._request("GET", "/api/v1/task-types")
        return [TaskTypeView.model_validate(item) for item in payload]

    def create_run(self, request: AnalysisRequest) -> str:
        payload = self._request(
            "POST",
            "/api/v1/analysis-runs",
            json=request.model_dump(mode="json"),
        )
        return str(payload["run_id"])

    def get_run(self, run_id: str) -> AnalysisRun:
        payload = self._request("GET", f"/api/v1/analysis-runs/{run_id}")
        return AnalysisRun.model_validate(payload)

    def list_runs(
        self,
        *,
        ticker: str | None = None,
        task_type: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> RunPage:
        params = {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in {
                "ticker": ticker,
                "task_type": task_type,
                "status": status,
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
                "offset": offset,
            }.items()
            if value is not None
        }
        payload = self._request("GET", "/api/v1/analysis-runs", params=params)
        return RunPage(
            items=tuple(
                AnalysisRun.model_validate(item) for item in payload.get("items", [])
            ),
            total=int(payload.get("total", 0)),
            limit=int(payload.get("limit", limit)),
            offset=int(payload.get("offset", offset)),
        )

    def get_nodes(self, run_id: str) -> list[NodeView]:
        payload = self._request(
            "GET", f"/api/v1/analysis-runs/{run_id}/nodes"
        )
        return [NodeView.model_validate(item) for item in payload.get("items", [])]

    def get_report(self, run_id: str) -> ReportView:
        payload = self._request(
            "GET", f"/api/v1/analysis-runs/{run_id}/report"
        )
        return ReportView(
            run_id=str(payload["run_id"]),
            markdown=str(payload["report_markdown"]),
            created_at=payload.get("created_at"),
        )

    def get_market_chart(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MarketChart:
        params = {
            "ticker": ticker.strip().upper(),
            **(
                {"start_date": start_date.isoformat()} if start_date else {}
            ),
            **({"end_date": end_date.isoformat()} if end_date else {}),
        }
        payload = self._request("GET", "/api/v1/market-bars", params=params)
        bars = tuple(MarketBar.model_validate(item) for item in payload.get("items", []))
        sources = tuple(dict.fromkeys(bar.source for bar in bars))
        return MarketChart(
            ticker=str(payload.get("ticker") or ticker).upper(),
            bars=bars,
            source=", ".join(sources) or None,
        )


def create_gateway(
    settings: Mapping[str, str] | None = None,
) -> ApiAnalysisGateway:
    resolved = load_settings() if settings is None else settings
    base_url = resolved.get(
        "DLP_API_BASE_URL", "http://127.0.0.1:8000"
    ).strip()
    return ApiAnalysisGateway(base_url or "http://127.0.0.1:8000")

