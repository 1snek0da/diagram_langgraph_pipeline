"""Immutable view models shared by the Streamlit pages."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from ..api.schemas import NodeRole, RunStatus
from ..routing import TaskType


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class TaskTypeView(FrozenModel):
    task_type: TaskType
    display_name: str
    description: str
    required_nodes: tuple[str, ...] = ()
    support_nodes: tuple[str, ...] = ()
    optional_nodes: tuple[str, ...] = ()
    skipped_nodes: tuple[str, ...] = ()
    required_inputs: tuple[str, ...] = ()
    conclusion_scope: str
    paid_sources_available: bool = False


class AnalysisRequest(FrozenModel):
    ticker: str = Field(min_length=1)
    task_type: TaskType
    industry_name: str | None = None
    as_of_date: date = Field(default_factory=date.today)
    investment_horizon: Literal["short", "medium", "long"] = "medium"
    report_days: int = Field(default=70, ge=5, le=2000)
    technical_days: int = Field(default=251, ge=5, le=2000)
    benchmark: str | None = None
    sector_index: str | None = None
    llm: bool | None = None
    offline: bool = False
    refresh: bool = False
    allow_paid: bool = False

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank")
        return normalized

    @field_validator("industry_name", "benchmark", "sector_index")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_windows_and_modes(self) -> Self:
        if self.technical_days < self.report_days:
            raise ValueError(
                "technical_days must be greater than or equal to report_days"
            )
        if self.offline and self.refresh:
            raise ValueError("offline and refresh are mutually exclusive")
        return self


class AnalysisRun(FrozenModel):
    run_id: str
    ticker: str
    task_type: TaskType
    status: RunStatus
    industry_name: str | None = None
    as_of_date: date | None = None
    investment_horizon: str = "medium"
    error_code: str | None = None
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class RunPage(FrozenModel):
    items: tuple[AnalysisRun, ...]
    total: int = 0
    limit: int = 20
    offset: int = 0

    def __iter__(self) -> Iterator[AnalysisRun]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> AnalysisRun:
        return self.items[index]


class NodeView(FrozenModel):
    name: str
    role: NodeRole
    status: str
    attempt_no: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_summary: str | None = None


class ReportView(FrozenModel):
    run_id: str
    markdown: str
    created_at: datetime | None = None


class MarketBar(FrozenModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None = None
    volume: float | None = None
    turnover_amount: float | None = None
    turnover_rate: float | None = None
    source: str


class MarketChart(FrozenModel):
    ticker: str
    bars: tuple[MarketBar, ...]
    source: str | None = None
    updated_at: datetime | None = None

