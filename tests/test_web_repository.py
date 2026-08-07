from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from diagram_langgraph_pipeline.providers.postgres_repository import (
    PostgresAnalysisRepository,
)


@dataclass
class SqlCall:
    sql: str
    params: tuple[object, ...] | None


class ScriptedCursor:
    def __init__(self) -> None:
        self.calls: list[SqlCall] = []
        self.rows: deque[object] = deque()
        self.rowcount = 0

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.calls.append(SqlCall(sql, params))

    def fetchone(self):
        return self.rows.popleft() if self.rows else None

    def fetchall(self):
        return self.rows.popleft() if self.rows else []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ScriptedConnection:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self.cursor_value = cursor

    def cursor(self) -> ScriptedCursor:
        return self.cursor_value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@pytest.fixture
def cursor() -> ScriptedCursor:
    return ScriptedCursor()


@pytest.fixture
def repository(cursor: ScriptedCursor) -> PostgresAnalysisRepository:
    result = object.__new__(PostgresAnalysisRepository)
    result._connect = lambda: ScriptedConnection(cursor)  # type: ignore[method-assign]
    return result


def test_create_pending_run_uses_placeholder_metadata(repository, cursor):
    cursor.rows.extend((None, ("industry-id",)))
    repository.create_pending_run(
        "00000000-0000-0000-0000-000000000001",
        {
            "ticker": "AAPL",
            "industry_name": "Unknown",
            "as_of_date": date(2026, 8, 6),
            "investment_horizon": "medium",
            "task_type": "technical",
            "user_request": "",
            "max_retries": 1,
        },
    )
    sql_text = "\n".join(call.sql.lower() for call in cursor.calls)
    assert "insert into industries" in sql_text
    assert "insert into securities" in sql_text
    assert "insert into analysis_runs" in sql_text
    assert "'pending'" in sql_text


def test_update_run_lifecycle_sanitizes_error_summary(repository, cursor):
    repository.update_run_lifecycle("run-id", "failed", error_code="upstream_error", error_summary="x" * 501)

    assert cursor.calls[-1].params == ("failed", "upstream_error", "x" * 500, "run-id")


def test_interrupt_incomplete_runs_returns_affected_count(repository, cursor):
    cursor.rowcount = 2
    assert repository.interrupt_incomplete_runs() == 2
    assert "status='interrupted'" in cursor.calls[-1].sql.replace(" ", "").lower()


def test_get_run_record_returns_json_ready_values(repository, cursor):
    cursor.rows.append(
        (
            "run-id", "AAPL", "Technology", date(2026, 8, 6), "medium", "full",
            "request", "completed", 0, 2, None, None,
            datetime(2026, 8, 6, tzinfo=timezone.utc),
            datetime(2026, 8, 7, tzinfo=timezone.utc),
        )
    )

    record = repository.get_run_record("run-id")

    assert record == {
        "id": "run-id", "ticker": "AAPL", "industry_name": "Technology",
        "as_of_date": "2026-08-06", "investment_horizon": "medium", "task_type": "full",
        "user_request": "request", "status": "completed", "retry_count": 0,
        "max_retries": 2, "error_code": None, "error_summary": None,
        "created_at": "2026-08-06T00:00:00+00:00",
        "updated_at": "2026-08-07T00:00:00+00:00",
    }
    assert cursor.calls[-1].params == ("run-id",)


def test_list_run_records_clamps_limit_binds_filters_and_returns_count(repository, cursor):
    cursor.rows.extend(
        (
            (7,),
            [
                (
                    "run-id", "AAPL", "Technology", date(2026, 8, 6), "medium", "technical",
                    "request", "completed", 0, 1, None, None,
                    datetime(2026, 8, 6, tzinfo=timezone.utc),
                    datetime(2026, 8, 7, tzinfo=timezone.utc),
                )
            ],
        )
    )

    records, total = repository.list_run_records(
        ticker="aapl", task_type="technical", status="completed",
        date_from=date(2026, 8, 1), date_to=date(2026, 8, 7), limit=500, offset=-3,
    )

    assert total == 7
    assert records[0]["as_of_date"] == "2026-08-06"
    count_call, list_call = cursor.calls
    assert count_call.params == ("AAPL", "technical", "completed", date(2026, 8, 1), date(2026, 8, 7))
    assert list_call.params == (*count_call.params, 100, 0)
    assert "%s" in count_call.sql


def test_list_node_records_returns_json_ready_values(repository, cursor):
    cursor.rows.append(
        [
            (
                "node-id", "planner", 1, "completed",
                datetime(2026, 8, 6, tzinfo=timezone.utc), None, None,
                {"input": Decimal("1.25")}, {"output": date(2026, 8, 6)},
            )
        ]
    )

    records = repository.list_node_records("run-id")

    assert records == [
        {
            "id": "node-id", "node_name": "planner", "attempt_no": 1,
            "status": "completed", "started_at": "2026-08-06T00:00:00+00:00",
            "ended_at": None, "error_message": None,
            "input": {"input": "1.25"}, "output": {"output": "2026-08-06"},
        }
    ]


def test_get_report_record_returns_json_ready_values(repository, cursor):
    cursor.rows.append(("report-id", "run-id", "# Report", "report.md", datetime(2026, 8, 6, tzinfo=timezone.utc)))

    record = repository.get_report_record("run-id")

    assert record == {
        "id": "report-id", "run_id": "run-id", "report_markdown": "# Report",
        "report_path": "report.md", "created_at": "2026-08-06T00:00:00+00:00",
    }


def test_get_market_bar_records_uses_optional_bound_dates(repository, cursor):
    cursor.rows.append(
        [
            (
                date(2026, 8, 6), Decimal("1.1"), Decimal("2.2"), Decimal("1.0"),
                Decimal("2.0"), Decimal("2.0"), Decimal("100"), None, None, "yfinance",
            )
        ]
    )

    records = repository.get_market_bar_records("aapl", date(2026, 8, 1), date(2026, 8, 6))

    assert records == [
        {
            "trade_date": "2026-08-06", "open": "1.1", "high": "2.2", "low": "1.0",
            "close": "2.0", "adj_close": "2.0", "volume": "100",
            "turnover_amount": None, "turnover_rate": None, "source": "yfinance",
        }
    ]
    assert cursor.calls[-1].params == ("AAPL", date(2026, 8, 1), date(2026, 8, 6))
