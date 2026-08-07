"""Public, path-safe request and response models for the web API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from ..routing import TaskType
from ..service import RunOptions


RunStatus = Literal[
    "pending", "running", "completed", "degraded", "failed", "interrupted"
]
NodeRole = Literal["required", "support", "optional", "skipped"]


class ApiModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class CreateAnalysisRunRequest(ApiModel):
    ticker: str = Field(min_length=1)
    task_type: TaskType = TaskType.FULL
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

    def to_options(self, run_id: str) -> RunOptions:
        return RunOptions(
            ticker=self.ticker,
            task_type=self.task_type,
            industry_name=self.industry_name,
            report_days=self.report_days,
            technical_days=self.technical_days,
            as_of=self.as_of_date,
            benchmark=self.benchmark,
            sector_index=self.sector_index,
            horizon=self.investment_horizon,
            llm=self.llm,
            offline=self.offline,
            refresh=self.refresh,
            allow_paid=self.allow_paid,
            run_id=run_id,
        )


class TaskTypeResponse(ApiModel):
    task_type: TaskType
    display_name: str
    description: str
    required_nodes: tuple[str, ...]
    support_nodes: tuple[str, ...]
    optional_nodes: tuple[str, ...]
    skipped_nodes: tuple[str, ...]
    required_inputs: tuple[str, ...]
    conclusion_scope: str
    paid_sources_available: bool


class AcceptedRunResponse(ApiModel):
    run_id: UUID
    status: Literal["pending"] = "pending"
    poll_url: str


class RunResponse(ApiModel):
    run_id: str
    ticker: str
    industry_name: str | None = None
    as_of_date: date
    investment_horizon: str
    task_type: TaskType
    user_request: str | None = None
    status: RunStatus
    retry_count: int = 0
    max_retries: int = 0
    error_code: str | None = None
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class RunListResponse(ApiModel):
    items: tuple[RunResponse, ...]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class NodeResponse(ApiModel):
    name: str
    role: NodeRole
    status: str
    attempt_no: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_summary: str | None = None


class NodeListResponse(ApiModel):
    items: tuple[NodeResponse, ...]


class ReportResponse(ApiModel):
    run_id: str
    report_markdown: str
    created_at: datetime


class MarketBarResponse(ApiModel):
    trade_date: date
    open: str
    high: str
    low: str
    close: str
    adj_close: str | None = None
    volume: str | None = None
    turnover_amount: str | None = None
    turnover_rate: str | None = None
    source: str


class MarketBarsResponse(ApiModel):
    ticker: str
    items: tuple[MarketBarResponse, ...]


class ErrorDetail(ApiModel):
    code: str
    message: str
    retryable: bool = False


class ErrorEnvelope(ApiModel):
    error: ErrorDetail

