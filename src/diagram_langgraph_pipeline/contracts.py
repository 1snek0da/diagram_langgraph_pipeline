"""Dependency contracts used by graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal, Protocol

from .schemas.research import DatasetKind, SourceBatch, SourceRequest


@dataclass(frozen=True)
class LLMResponse:
    """Normalized language-model response without provider SDK objects."""

    text: str
    model: str
    provider: str
    request_id: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderPolicy:
    """Runtime policy used by the CLI and cache wrapper."""

    cost_tier: Literal["free", "local", "metered", "paid"] = "free"
    ttl_seconds: int = 86_400
    cache_mode: Literal["full", "metadata_only", "disabled"] = "full"


@dataclass(frozen=True)
class RunEvent:
    event_type: str
    stage: str
    status: Literal["started", "completed", "degraded", "failed"]
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RunEventSink(Protocol):
    def emit(self, event: RunEvent) -> None:
        """Publish a credential-free progress event."""


class DataCacheRepository(Protocol):
    def check_health(self) -> dict[str, Any]: ...

    def load_security(self, ticker: str) -> dict[str, Any] | None: ...

    def upsert_security_metadata(self, payload: dict[str, Any]) -> None: ...

    def load_market_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        *,
        intraday_interval: str,
    ) -> dict[str, Any]: ...

    def save_market_cache(self, ticker: str, payload: dict[str, Any]) -> None: ...


class ResearchResponseCache(Protocol):
    def load_research_cache(
        self,
        provider: str,
        dataset_kind: str,
        scope_hash: str,
        as_of_date: date,
        start_date: date | None,
        end_date: date | None,
        *,
        allow_expired: bool = False,
    ) -> dict[str, Any] | None: ...

    def save_research_cache(self, payload: dict[str, Any]) -> None: ...


class LanguageModelProvider(Protocol):
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Generate an advisory response from a bounded list of text messages."""


class MarketDataProvider(Protocol):
    def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Return daily bars, optional minute bars, valuations, and source metadata."""


class ResearchSourceAdapter(Protocol):
    name: str
    capabilities: frozenset[DatasetKind]

    def fetch(self, request: SourceRequest) -> SourceBatch:
        """Fetch one normalized source batch without mutating graph state."""


class ResearchDataProvider(Protocol):
    def fetch(self, request: SourceRequest) -> SourceBatch:
        """Return a normalized, source-aware batch for one research dataset."""


class AnalysisRepository(Protocol):
    def record_provider_fetch(
        self,
        run_id: str,
        provider: str,
        dataset_kind: str,
        request_payload: dict[str, Any],
        response_summary: dict[str, Any],
    ) -> None:
        """Persist one source fetch summary without credentials or full content."""

    def record_node_run(
        self,
        run_id: str,
        node_name: str,
        status: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        error_message: str | None = None,
    ) -> None:
        """Persist one node execution record."""

    def save_final_report(self, run_id: str, report_markdown: str) -> None:
        """Persist a final Markdown report."""

    def record_llm_invocation(
        self, run_id: str, node_name: str, payload: dict[str, Any]
    ) -> None:
        """Persist one credential-free model invocation audit record."""
