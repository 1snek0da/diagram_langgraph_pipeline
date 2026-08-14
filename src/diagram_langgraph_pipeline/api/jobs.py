"""Bounded background execution for API-submitted analysis runs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping
from uuid import UUID, uuid4

from ..service import RunOptions, run_analysis
from .schemas import CreateAnalysisRunRequest


Runner = Callable[
    [RunOptions, Mapping[str, str]],
    tuple[dict[str, Any], dict[str, Any]],
]


class AnalysisJobService:
    def __init__(
        self,
        repository: Any,
        settings: Mapping[str, str],
        *,
        runner: Runner = run_analysis,
        executor: Any = None,
        max_workers: int = 1,
    ) -> None:
        if not 1 <= max_workers <= 8:
            raise ValueError("max_workers must be between 1 and 8")
        self._repository = repository
        self._settings = dict(settings)
        self._runner = runner
        self._executor = executor or ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="analysis-job",
        )

    def submit(self, request: CreateAnalysisRunRequest) -> UUID:
        run_id = uuid4()
        run_id_text = str(run_id)
        options = request.to_options(run_id_text)
        self._repository.create_pending_run(
            run_id_text,
            request.model_dump(mode="json"),
        )
        self._executor.submit(self._execute, options)
        return run_id

    def _execute(self, options: RunOptions) -> None:
        run_id = str(options.run_id)
        self._repository.update_run_lifecycle(run_id, "running")
        try:
            _state, summary = self._runner(options, self._settings)
        except Exception as exc:
            self._repository.update_run_lifecycle(
                run_id,
                "failed",
                error_code="ANALYSIS_FAILED",
                error_summary=type(exc).__name__,
            )
            return

        optional_statuses = summary.get("optional_node_statuses", {})
        degraded = any(
            isinstance(item, Mapping)
            and item.get("status") in {"skipped", "degraded"}
            for item in optional_statuses.values()
        )
        self._repository.update_run_lifecycle(
            run_id,
            "degraded" if degraded else "completed",
        )

    def recover(self) -> int:
        return int(self._repository.interrupt_incomplete_runs())

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
