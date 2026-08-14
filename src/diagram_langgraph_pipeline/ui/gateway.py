"""Stable dependency boundary used by Streamlit pages."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .models import (
    AnalysisRequest,
    AnalysisRun,
    MarketChart,
    NodeView,
    ReportView,
    RunPage,
    TaskTypeView,
)


class AnalysisGateway(Protocol):
    def task_types(self) -> list[TaskTypeView]: ...

    def create_run(self, request: AnalysisRequest) -> str: ...

    def get_run(self, run_id: str) -> AnalysisRun: ...

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
    ) -> RunPage: ...

    def get_nodes(self, run_id: str) -> list[NodeView]: ...

    def get_report(self, run_id: str) -> ReportView: ...

    def get_market_chart(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MarketChart: ...

