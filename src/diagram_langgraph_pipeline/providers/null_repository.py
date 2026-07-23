"""No-op repository used when persistence is not configured."""

from __future__ import annotations

from typing import Any


class NullRepository:
    def record_provider_fetch(
        self,
        run_id: str,
        provider: str,
        dataset_kind: str,
        request_payload: dict[str, Any],
        response_summary: dict[str, Any],
    ) -> None:
        return None

    def record_node_run(
        self,
        run_id: str,
        node_name: str,
        status: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        error_message: str | None = None,
    ) -> None:
        return None

    def save_final_report(self, run_id: str, report_markdown: str) -> None:
        return None
