"""Validated research-source and node-boundary data models."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatasetKind(str, Enum):
    INDUSTRY_REPORTS = "industry_reports"
    CAPEX = "capex"
    POLICY = "policy"
    INDUSTRY_VALUATION = "industry_valuation"
    COMPANY_PROFILE = "company_profile"
    PROFIT_FORECASTS = "profit_forecasts"
    MARGINAL_EVENTS = "marginal_events"
    COMPANY_VALUATION = "company_valuation"
    SENTIMENT = "sentiment"
    FX = "fx"
    ANNOUNCEMENTS = "announcements"
    MARKET_VALUATION = "market_valuation"
    INDUSTRY_MEMBERS = "industry_members"


class FactBasis(str, Enum):
    REPORTED = "reported"
    EXTRACTED = "extracted"
    ESTIMATED = "estimated"
    DERIVED = "derived"


class SourceTier(str, Enum):
    PRIMARY_OFFICIAL = "primary_official"
    LICENSED_STRUCTURED = "licensed_structured"
    LICENSED_REPORT = "licensed_report"
    SECONDARY_NEWS = "secondary_news"
    MANUAL = "manual"


class EntityRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    name: str
    ticker: str | None = None
    cik: str | None = None
    role: Literal["demand", "supply", "target", "peer", "other"] = "other"

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(character for character in value if character.isdigit())
        return digits.zfill(10) if digits else None


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_kind: DatasetKind
    run_id: str
    as_of_date: date
    industry_code: str | None = None
    industry_name: str | None = None
    entities: list[EntityRef] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    history_years: int = Field(default=5, ge=1, le=20)
    forecast_years: list[int] = Field(default_factory=list)
    base_currency: str = Field(default="CNY", min_length=3, max_length=3)
    topic: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def fill_and_validate_dates(self) -> "SourceRequest":
        if not self.forecast_years:
            self.forecast_years = [self.as_of_date.year + 1, self.as_of_date.year + 2]
        if self.end_date is None:
            self.end_date = self.as_of_date
        if self.end_date > self.as_of_date:
            raise ValueError("end_date cannot be later than as_of_date")
        if self.start_date and self.start_date > self.end_date:
            raise ValueError("start_date cannot be later than end_date")
        return self


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(default_factory=lambda: str(uuid4()))
    provider: str
    source_tier: SourceTier
    source_type: str
    external_id: str | None = None
    title: str
    publisher: str | None = None
    published_at: datetime | None = None
    url: str | None = None
    file_path: str | None = None
    content_hash: str
    language: str = "zh-CN"
    license_scope: str = "public"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str = "input"
    evidence_type: str = "research"
    claim_text: str
    quote_text: str | None = None
    page_no: int | None = Field(default=None, ge=1)
    paragraph_ref: str | None = None
    metric_key: str | None = None
    extraction_method: str = "provided"
    confidence_score: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    metric_key: str
    entity_id: str
    period_start: date | None = None
    period_end: date | None = None
    fiscal_year: int | None = None
    value: Decimal | None
    currency: str | None = None
    unit: str = "absolute"
    scale: Decimal = Decimal("1")
    basis: FactBasis
    provider: str
    source_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    confidence_score: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class CoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_items: list[str] = Field(default_factory=list)
    available_items: list[str] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)
    coverage_ratio: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    latest_published_at: datetime | None = None
    source_errors: list[str] = Field(default_factory=list)

    @classmethod
    def from_items(
        cls,
        requested: list[str],
        available: list[str],
        *,
        errors: list[str] | None = None,
    ) -> "CoverageReport":
        requested_unique = list(dict.fromkeys(requested))
        available_unique = list(dict.fromkeys(available))
        missing = [
            item for item in requested_unique if item not in set(available_unique)
        ]
        covered = set(requested_unique) & set(available_unique)
        ratio = (
            Decimal(len(covered)) / Decimal(len(requested_unique))
            if requested_unique
            else Decimal("1")
        )
        return cls(
            requested_items=requested_unique,
            available_items=available_unique,
            missing_items=missing,
            coverage_ratio=ratio,
            source_errors=errors or [],
        )


class SourceBatch(BaseModel):
    """Standard provider response plus validated topic-specific node data."""

    model_config = ConfigDict(extra="forbid")

    data: dict[str, Any] = Field(default_factory=dict)
    documents: list[SourceDocument] = Field(default_factory=list)
    facts: list[MetricFact] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TopicInputBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceItem] = Field(default_factory=list)


class IndustryReportInput(TopicInputBase):
    summary: str = "未提供行业研报摘要"
    market_size: Decimal | None = None
    value_chain: dict[str, Any] = Field(default_factory=dict)
    technology_routes: list[str] = Field(default_factory=list)
    key_data: list[Any] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)
    policy_leads: list[dict[str, Any]] = Field(default_factory=list)
    capex_facts: list[dict[str, Any]] = Field(default_factory=list)


class CapexRecordInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    company_name: str
    entity_id: str | None = None
    role: Literal["demand", "supply", "other"] = "other"
    fiscal_year: int | None = None
    total_capex: Decimal | None = None
    communication_capex: Decimal | None = None
    currency: str = "USD"
    unit: str = "currency"
    scale: Decimal = Decimal("1")
    fact_basis: FactBasis = FactBasis.REPORTED
    total_capex_basis: FactBasis | None = None
    communication_capex_basis: FactBasis | None = None
    capex_change_pct: Decimal | None = None
    source_id: str | None = None


class CapexConsensusForecastInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    forecast_year: int
    scenario_name: Literal["bear", "base", "bull"] = "base"
    communication_capex: Decimal
    currency: str = "USD"
    published_at: datetime
    institution: str
    source_id: str
    fact_basis: FactBasis = FactBasis.ESTIMATED


class UpstreamCapexInput(TopicInputBase):
    records: list[CapexRecordInput] = Field(default_factory=list)
    consensus_forecasts: list[CapexConsensusForecastInput] = Field(default_factory=list)
    direction: Literal["up", "flat", "down", "unknown"] | None = None
    demand_signal: str = "证据不足"


class PolicyEventInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    published_at: datetime | None = None
    direction: Literal["positive", "neutral", "negative"] | None = None
    magnitude: Literal["small", "large", "unknown"] = "unknown"
    impact_horizon: str = "unknown"
    affected_metrics: list[str] = Field(default_factory=list)
    quantified_impact_pct: Decimal | None = None
    source_id: str | None = None


class PolicyInput(TopicInputBase):
    direction: Literal[
        "positive", "neutral", "negative", "supportive", "restrictive"
    ] = "neutral"
    magnitude: Literal["small", "large", "unknown"] = "unknown"
    impact_horizon: str = "unknown"
    affected_metrics: list[str] = Field(default_factory=list)
    quantified_impact_pct: Decimal | None = None
    summary: str = "未提供可核验政策资料"
    events: list[PolicyEventInput] = Field(default_factory=list)


class IndustryValuationInput(TopicInputBase):
    current_market_cap: Decimal | None = None
    current_market_cap_currency: str = "CNY"
    addressable_share_low: Decimal = Field(default=Decimal("0.35"), ge=0, le=1)
    addressable_share_high: Decimal = Field(default=Decimal("0.40"), ge=0, le=1)
    net_margin: Decimal = Field(default=Decimal("0.30"), ge=0, le=1)
    pe_low: Decimal = Field(default=Decimal("30"), gt=0)
    pe_high: Decimal = Field(default=Decimal("35"), gt=0)
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[Any] = Field(default_factory=list)
    confidence_score: Decimal | None = Field(default=None, ge=0, le=1)
    universe_id: str | None = None
    universe_as_of_date: date | None = None
    fx_rate_usd_cny: Decimal | None = Field(default=None, gt=0)
    fx_rate_date: date | None = None


class CompanyBusinessInput(TopicInputBase):
    business_summary: str = "未提供公司业务资料"
    revenue_segments: list[dict[str, Any]] = Field(default_factory=list)
    industry_linkage: str = "unknown"
    growth_drivers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    company_type: Literal[
        "optical_chip",
        "optical_module",
        "optical_component",
        "communication_equipment",
        "pcb_connector",
        "unknown",
    ] = "unknown"
    market_share_rank: int | None = Field(default=None, ge=1)
    classification_evidence: list[EvidenceItem] = Field(default_factory=list)


class ProfitForecastRecordInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    forecast_year: int
    institution: str | None = None
    published_at: datetime | None = None
    forecast_basis: Literal[
        "company_guidance", "broker", "consensus", "model", "manual"
    ] = "manual"
    currency: str = "CNY"
    revenue_forecast: Decimal | None = None
    net_profit_forecast: Decimal | None = None
    eps_forecast: Decimal | None = None
    pe_assumption: Decimal | None = None
    revision_pct: Decimal | None = None
    source_id: str | None = None


class ProfitForecastInput(TopicInputBase):
    forecasts: list[ProfitForecastRecordInput] = Field(default_factory=list)
    revision_direction: Literal["up", "unchanged", "down"] | None = None
    consensus_summary: str = "未提供一致预期"
    quarterly_financials: list[dict[str, Any]] = Field(default_factory=list)
    product_information: dict[str, Any] = Field(default_factory=dict)


class MarginalEventInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_type: Literal[
        "order",
        "certification",
        "capacity",
        "customer",
        "product",
        "management",
        "policy",
        "other",
    ]
    event_summary: str
    event_date: date | None = None
    published_at: datetime | None = None
    impact_direction: Literal["positive", "neutral", "negative"] = "neutral"
    certainty: Literal["low", "medium", "high"] = "medium"
    impact_horizon: str = "unknown"
    source_id: str | None = None


class MarginalChangeInput(TopicInputBase):
    events: list[MarginalEventInput] = Field(default_factory=list)
    direction: Literal["positive", "neutral", "negative"] | None = None
    certainty: Literal["low", "medium", "high"] | None = None
    impact_horizon: str | None = None


class CompanyValuationInput(TopicInputBase):
    current_market_cap: Decimal | None = None
    current_market_cap_currency: str = "CNY"
    forecast_profit: Decimal | None = None
    forecast_profit_currency: str = "CNY"
    base_pe: Decimal | None = None
    assumptions: list[Any] = Field(default_factory=list)
    confidence_score: Decimal | None = Field(default=None, ge=0, le=1)


class SentimentInput(TopicInputBase):
    sentiment_score: Decimal = Field(default=Decimal("0"), ge=-1, le=1)
    heat_score: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    positive_items: list[Any] = Field(default_factory=list)
    negative_items: list[Any] = Field(default_factory=list)


ResearchTopicInput = (
    IndustryReportInput
    | UpstreamCapexInput
    | PolicyInput
    | IndustryValuationInput
    | CompanyBusinessInput
    | ProfitForecastInput
    | MarginalChangeInput
    | CompanyValuationInput
    | SentimentInput
)


TOPIC_MODELS: dict[str, type[BaseModel]] = {
    "industry_report": IndustryReportInput,
    "upstream_capex": UpstreamCapexInput,
    "policy": PolicyInput,
    "industry_valuation": IndustryValuationInput,
    "business": CompanyBusinessInput,
    "profit_forecast": ProfitForecastInput,
    "marginal_change": MarginalChangeInput,
    "company_valuation": CompanyValuationInput,
    "sentiment": SentimentInput,
}


def topic_model_for(topic: str) -> type[BaseModel]:
    try:
        return TOPIC_MODELS[topic]
    except KeyError as exc:
        raise ValueError(f"unsupported research topic: {topic}") from exc
