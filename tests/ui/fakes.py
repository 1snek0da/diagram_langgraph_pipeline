from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from diagram_langgraph_pipeline.api.catalog import task_catalog
from diagram_langgraph_pipeline.ui.models import (
    AnalysisRequest,
    AnalysisRun,
    MarketBar,
    MarketChart,
    NodeView,
    ReportView,
    RunPage,
    TaskTypeView,
)


class FakeGateway:
    def __init__(
        self,
        *,
        task_types=None,
        runs=None,
        run=None,
        nodes=None,
        report=None,
        market_chart=None,
    ):
        self._task_types = task_types or []
        self._runs = runs or []
        self._run = run
        self._nodes = nodes or []
        self._report = report
        self._market_chart = market_chart
        self.created_request: AnalysisRequest | None = None
        self.get_run_calls: list[str] = []
        self.last_filters = None

    def task_types(self):
        return self._task_types

    def create_run(self, request):
        self.created_request = request
        return "run-created"

    def get_run(self, run_id):
        self.get_run_calls.append(run_id)
        return self._run

    def list_runs(self, **filters):
        self.last_filters = {
            key: value
            for key, value in filters.items()
            if value is not None and not (key == "limit" and value == 20)
            and not (key == "offset" and value == 0)
        }
        return RunPage(
            items=tuple(self._runs),
            total=len(self._runs),
            limit=filters.get("limit", 20),
            offset=filters.get("offset", 0),
        )

    def get_nodes(self, run_id):
        return self._nodes

    def get_report(self, run_id):
        return self._report

    def get_market_chart(self, ticker, start_date=None, end_date=None):
        return self._market_chart


@dataclass
class DownloadRecord:
    label: str
    data: Any
    file_name: str
    mime: str | None


class FakeStreamlit:
    def __init__(self, *, submit=False, values=None, buttons=None):
        self.submit = submit
        self.values = values or {}
        self.buttons = buttons or {}
        self.session_state = {}
        self.rendered_text: list[str] = []
        self.plotly_figures: list[Any] = []
        self.downloads: list[DownloadRecord] = []
        self.metrics: list[tuple[str, Any]] = []
        self.frames: list[Any] = []
        self.segmented_controls: list[tuple[str, tuple[Any, ...]]] = []
        self.rerun_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def columns(self, count, **_kwargs):
        return [self for _ in range(count if isinstance(count, int) else len(count))]

    def form(self, *_args, **_kwargs):
        return self

    def expander(self, *_args, **_kwargs):
        return self

    def spinner(self, *_args, **_kwargs):
        return self

    def _value(self, label, default):
        return self.values.get(label, default)

    def selectbox(self, label, options, index=0, format_func=None, **_kwargs):
        selected = self._value(label, options[index])
        for option in options:
            if option == selected or getattr(option, "value", None) == selected:
                return option
            if getattr(option, "task_type", None) == selected:
                return option
        return selected

    def segmented_control(self, label, options, default=None, **_kwargs):
        options = tuple(options)
        self.segmented_controls.append((label, options))
        return self._value(label, default)

    def text_input(self, label, value="", **_kwargs):
        return self._value(label, value)

    def date_input(self, label, value=None, **_kwargs):
        return self._value(label, value)

    def checkbox(self, label, value=False, **_kwargs):
        return self._value(label, value)

    def number_input(self, label, value=0, **_kwargs):
        return self._value(label, value)

    def button(self, label, **_kwargs):
        return bool(self.buttons.get(label, False))

    def form_submit_button(self, *_args, **_kwargs):
        return self.submit

    def _render(self, value, **_kwargs):
        self.rendered_text.append(str(value))

    title = _render
    header = _render
    subheader = _render
    caption = _render
    markdown = _render
    write = _render
    error = _render
    warning = _render
    info = _render
    success = _render

    def metric(self, label, value, **_kwargs):
        self.metrics.append((label, value))

    def dataframe(self, value, **_kwargs):
        self.frames.append(value)

    def plotly_chart(self, figure, **_kwargs):
        self.plotly_figures.append(figure)

    def download_button(self, label, data, file_name, mime=None, **_kwargs):
        self.downloads.append(DownloadRecord(label, data, file_name, mime))

    def rerun(self):
        self.rerun_count += 1

    def set_page_config(self, **_kwargs):
        return None

    def text_for(self, token):
        return " ".join(self.rendered_text)


def five_task_views() -> list[TaskTypeView]:
    return [
        TaskTypeView.model_validate(record.model_dump())
        for record in task_catalog(paid_sources_available=False)
    ]


def sample_market_chart() -> MarketChart:
    return MarketChart(
        ticker="AAPL",
        source="fixture",
        bars=(
            MarketBar(
                trade_date=date(2026, 8, 5),
                open=100,
                high=103,
                low=99,
                close=102,
                volume=1000,
                source="fixture",
            ),
            MarketBar(
                trade_date=date(2026, 8, 6),
                open=102,
                high=105,
                low=101,
                close=104,
                volume=1200,
                source="fixture",
            ),
        ),
    )
