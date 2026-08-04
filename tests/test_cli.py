import json
from pathlib import Path

from typer.testing import CliRunner

from diagram_langgraph_pipeline import cli
from diagram_langgraph_pipeline.service import infer_comparisons
from diagram_langgraph_pipeline.service import result_summary


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


def test_token_usage_check_explains_disabled_d4f(monkeypatch):
    messages = []

    class CapturingConsole:
        def print(self, value):
            messages.append(str(value))

    monkeypatch.setattr(cli, "stdout", CapturingConsole())
    cli._print_token_usage({"d4f_token_usage": {}})
    assert "未产生 D4F Token" in messages[0]
