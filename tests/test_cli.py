import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from diagram_langgraph_pipeline import cli
from diagram_langgraph_pipeline import service
from diagram_langgraph_pipeline.contracts import RunEvent
from diagram_langgraph_pipeline.routing import TaskType, get_execution_plan
from diagram_langgraph_pipeline.service import infer_comparisons
from diagram_langgraph_pipeline.service import RunOptions, result_summary, validate_options


runner = CliRunner()


def test_help_lists_hybrid_commands():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "data" in result.stdout
    assert "demo" in result.stdout


def test_no_arguments_on_non_tty_displays_help():
    result = runner.invoke(cli.app, [])
    assert result.exit_code == 0
    assert "Commands" in result.stdout


def test_run_rejects_technical_window_smaller_than_report_window(monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda: {})
    result = runner.invoke(
        cli.app,
        ["run", "AAPL", "--report-days", "70", "--technical-days", "20", "--no-llm"],
    )
    assert result.exit_code == 2
    assert "不得小于" in result.output


def test_json_mode_emits_one_structured_document(monkeypatch, tmp_path: Path):
    summary = {
        "run_id": "run-1",
        "ticker": "AAPL",
        "coverage": {},
        "provider_calls": {},
        "d4f_token_usage": {},
        "decision": {},
        "review": {},
        "report_path": str(tmp_path / "report.md"),
    }
    monkeypatch.setattr(cli, "load_settings", lambda: {})
    monkeypatch.setattr(cli, "paid_provider_names", lambda settings: [])
    monkeypatch.setattr(cli, "run_analysis", lambda *args, **kwargs: ({}, summary))

    result = runner.invoke(cli.app, ["run", "AAPL", "--json", "--no-llm"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["run_id"] == "run-1"


def test_run_accepts_explicit_task(monkeypatch, tmp_path: Path):
    captured = {}
    monkeypatch.setattr(cli, "load_settings", lambda: {})
    monkeypatch.setattr(cli, "paid_provider_names", lambda settings: [])

    def fake_run(options, settings, event_callback=None):
        captured["options"] = options
        return {}, {
            "run_id": "run-1",
            "ticker": "AAPL",
            "task_type": "technical",
            "coverage": {},
            "provider_calls": {},
            "d4f_token_usage": {},
            "decision": {},
            "review": {},
            "report_path": str(tmp_path / "report.md"),
            "enabled_nodes": [],
            "skipped_nodes": [],
            "completed_nodes": [],
            "failed_nodes": [],
            "conclusion_scope": "仅个股技术面，不给出完整买卖结论",
        }

    monkeypatch.setattr(cli, "run_analysis", fake_run)
    result = runner.invoke(
        cli.app, ["run", "AAPL", "--task", "technical", "--json", "--no-llm"]
    )

    assert result.exit_code == 0
    assert captured["options"].task_type is TaskType.TECHNICAL


def test_all_tasks_require_real_ticker():
    for task_type in TaskType:
        with pytest.raises(Exception, match="Ticker"):
            validate_options(RunOptions(ticker=None, task_type=task_type))


@pytest.mark.parametrize(
    "task_type", [TaskType.FULL, TaskType.FUNDAMENTAL, TaskType.TECHNICAL]
)
def test_stock_tasks_require_ticker(task_type):
    with pytest.raises(Exception, match="Ticker"):
        validate_options(RunOptions(ticker=None, task_type=task_type))


def test_industry_and_market_accept_ticker_without_industry_name():
    validate_options(RunOptions(ticker="AAPL", task_type=TaskType.INDUSTRY))
    validate_options(RunOptions(ticker="AAPL", task_type=TaskType.MARKET))


def test_plan_preview_lists_scope_and_skipped_count(monkeypatch):
    messages = []
    monkeypatch.setattr(
        cli,
        "stdout",
        type("Console", (), {"print": lambda self, value: messages.append(str(value))})(),
    )

    plan = get_execution_plan("technical")
    cli._print_task_plan(plan)

    rendered = "\n".join(messages)
    assert "technical" in rendered
    assert plan.conclusion_scope in rendered
    assert str(len(plan.skipped_nodes)) in rendered


def test_task_progress_printer_counts_terminal_node_events(monkeypatch):
    messages = []
    monkeypatch.setattr(
        cli,
        "stderr",
        type("Console", (), {"print": lambda self, value: messages.append(str(value))})(),
    )
    progress = cli._TaskProgressPrinter(get_execution_plan("technical"))

    progress(RunEvent("node", "planner", "started", "开始"))
    progress(RunEvent("node", "planner", "completed", "完成"))
    progress(RunEvent("node", "stock_data_fetch", "degraded", "缓存数据不完整"))

    assert any("1/" in message and "planner" in message for message in messages)
    assert any("2/" in message and "缓存数据不完整" in message for message in messages)


def test_market_service_skips_security_lookup_and_target_prefetch(monkeypatch, tmp_path):
    captured = {}

    class FakeRepository:
        def __init__(self, dsn):
            captured["dsn"] = dsn

        def check_health(self):
            return {"cache_schema_ready": True}

        def load_security(self, ticker):
            captured["loaded_ticker"] = ticker
            return {
                "ticker": ticker,
                "company_name": "Microsoft",
                "industry_name": "Software",
                "sector": "Technology",
                "external_ids": {},
            }

        def save_final_report(self, run_id, markdown):
            pass

        def update_report_path(self, run_id, path):
            pass

    class FakeMarketProvider:
        def __init__(self, *args, **kwargs):
            pass

        def fetch(self, ticker, start, end):
            raise AssertionError("market task must not prefetch a target ticker")

    def fake_run_research(initial_state, deps):
        captured["initial_state"] = initial_state
        return {
            **initial_state,
            "run_id": "run-1",
            "final_markdown": "# report",
            "completed_nodes": [],
            "failed_nodes": [],
        }

    monkeypatch.setattr(service, "PostgresAnalysisRepository", FakeRepository)
    monkeypatch.setattr(service, "DatabaseFirstMarketDataProvider", FakeMarketProvider)
    monkeypatch.setattr(service, "build_research_provider", lambda *args, **kwargs: object())
    monkeypatch.setattr(service, "build_optional_llm_provider", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "run_research", fake_run_research)

    _, summary = service.run_analysis(
        RunOptions(
            ticker="MSFT",
            task_type=TaskType.MARKET,
            benchmark="^GSPC",
            sector_index="XLK",
            llm=False,
            output=tmp_path / "market.md",
        ),
        {"DATABASE_URL": "postgresql://example"},
    )

    initial = captured["initial_state"]
    assert initial["task_type"] == "market"
    assert captured["loaded_ticker"] == "MSFT"
    assert initial["ticker"] == "MSFT"
    assert initial["company_name"] == "Microsoft"
    assert initial["benchmark_ticker"] == "^GSPC"
    assert initial["sector_index_ticker"] == "XLK"
    assert summary["coverage"]["daily_bars"] == 0


def test_industry_service_uses_real_ticker_metadata_without_target_prefetch(
    monkeypatch, tmp_path
):
    captured = {}

    class FakeRepository:
        def __init__(self, dsn):
            pass

        def check_health(self):
            return {"cache_schema_ready": True}

        def load_security(self, ticker):
            captured["loaded_ticker"] = ticker
            return {
                "ticker": ticker,
                "company_name": "Microsoft",
                "industry_name": "Software",
                "sector": "Technology",
                "external_ids": {},
            }

        def save_final_report(self, run_id, markdown):
            pass

        def update_report_path(self, run_id, path):
            pass

    class FakeMarketProvider:
        def __init__(self, *args, **kwargs):
            pass

        def fetch(self, ticker, start, end):
            raise AssertionError("industry task must not prefetch target bars")

    def fake_run_research(initial_state, deps):
        captured["initial_state"] = initial_state
        return {
            **initial_state,
            "run_id": "run-1",
            "final_markdown": "# report",
            "completed_nodes": [],
            "failed_nodes": [],
        }

    monkeypatch.setattr(service, "PostgresAnalysisRepository", FakeRepository)
    monkeypatch.setattr(service, "DatabaseFirstMarketDataProvider", FakeMarketProvider)
    monkeypatch.setattr(service, "build_research_provider", lambda *args, **kwargs: object())
    monkeypatch.setattr(service, "build_optional_llm_provider", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "run_research", fake_run_research)

    service.run_analysis(
        RunOptions(
            ticker="MSFT",
            task_type=TaskType.INDUSTRY,
            llm=False,
            output=tmp_path / "industry.md",
        ),
        {"DATABASE_URL": "postgresql://example"},
    )

    initial = captured["initial_state"]
    assert captured["loaded_ticker"] == "MSFT"
    assert initial["ticker"] == "MSFT"
    assert initial["company_name"] == "Microsoft"
    assert initial["industry_name"] == "Software"


def test_noninteractive_paid_provider_requires_explicit_authorization(monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda: {"TUSHARE_TOKEN": "hidden"})
    result = runner.invoke(cli.app, ["run", "AAPL", "--no-llm"])
    assert result.exit_code == 2
    assert "--allow-paid" in result.output


def test_data_status_json(monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda: {})
    monkeypatch.setattr(
        cli,
        "data_status",
        lambda *args: {"ticker": "0700.HK", "status": "complete"},
    )
    result = runner.invoke(cli.app, ["data", "status", "0700.HK", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ticker"] == "0700.HK"


def test_multi_market_comparison_inference():
    assert infer_comparisons("600519.SS", {}, None, None) == ("000300.SS", None)
    assert infer_comparisons("0700.HK", {}, None, None) == ("^HSI", None)
    assert infer_comparisons("AAPL", {"sector": "Technology"}, None, None) == (
        "^GSPC",
        "XLK",
    )


def test_result_summary_exposes_total_and_per_node_token_usage(tmp_path):
    summary = result_summary(
        {
            "run_id": "run-1",
            "ticker": "AAPL",
            "llm_node_results": {
                "planner": {
                    "status": "completed",
                    "model": "deepseek-v4-flash",
                    "usage": {
                        "prompt_tokens": 120,
                        "completion_tokens": 30,
                        "cached_tokens": 20,
                    },
                    "projection_manifest": {"estimated_prompt_tokens": 100},
                }
            },
        },
        {},
        tmp_path / "report.md",
    )
    usage = summary["d4f_token_usage"]
    assert usage["prompt_tokens"] == 120
    assert usage["completion_tokens"] == 30
    assert usage["cached_tokens"] == 20
    assert usage["total_tokens"] == 150
    assert usage["nodes"]["planner"]["estimated_prompt_tokens"] == 100


def test_result_summary_exposes_task_plan_progress(tmp_path):
    summary = result_summary(
        {
            "run_id": "run-1",
            "ticker": "AAPL",
            "task_type": "technical",
            "required_nodes": ["stock_data_analysis", "stock_technical"],
            "support_nodes": ["planner", "stock_data_fetch"],
            "optional_nodes": [],
            "skipped_nodes": ["decision"],
            "completed_nodes": ["planner", "stock_data_fetch"],
            "failed_nodes": [],
            "conclusion_scope": "仅个股技术面，不给出完整买卖结论",
        },
        {},
        tmp_path / "report.md",
    )

    assert summary["task_type"] == "technical"
    assert summary["enabled_nodes"] == [
        "stock_data_analysis",
        "stock_technical",
        "planner",
        "stock_data_fetch",
    ]
    assert summary["skipped_nodes"] == ["decision"]
    assert summary["completed_nodes"] == ["planner", "stock_data_fetch"]
    assert summary["failed_nodes"] == []
    assert summary["conclusion_scope"] == "仅个股技术面，不给出完整买卖结论"


def test_partial_summary_uses_conclusion_scope_instead_of_unknown_decision(monkeypatch):
    messages = []
    monkeypatch.setattr(
        cli,
        "stdout",
        type("Console", (), {"print": lambda self, value: messages.append(str(value))})(),
    )

    cli._print_summary(
        {
            "run_id": "run-1",
            "ticker": "AAPL",
            "task_type": "technical",
            "decision": {},
            "review": {"passed": True},
            "conclusion_scope": "仅个股技术面，不给出完整买卖结论",
        }
    )

    rendered = "\n".join(messages)
    assert "decision=unknown" not in rendered
    assert "仅个股技术面" in rendered


def test_token_usage_check_explains_disabled_d4f(monkeypatch):
    messages = []

    class CapturingConsole:
        def print(self, value):
            messages.append(str(value))

    monkeypatch.setattr(cli, "stdout", CapturingConsole())
    cli._print_token_usage({"d4f_token_usage": {}})
    assert "未产生 D4F Token" in messages[0]
