"""Dependency contracts used by graph nodes."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from .schemas.research import DatasetKind, SourceBatch, SourceRequest


class MarketDataProvider(Protocol):
    def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Return bars, valuation history, source name, and optional metadata."""


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
