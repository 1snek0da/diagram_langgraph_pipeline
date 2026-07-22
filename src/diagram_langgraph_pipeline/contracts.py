"""Dependency contracts used by graph nodes."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class MarketDataProvider(Protocol):
    def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Return bars, valuation history, source name, and optional metadata."""


class ResearchDataProvider(Protocol):
    def get_topic(self, topic: str, state: dict[str, Any]) -> dict[str, Any]:
        """Return normalized research input for one agent topic."""


class AnalysisRepository(Protocol):
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
