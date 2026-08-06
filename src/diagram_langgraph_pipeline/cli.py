"""Typer + Rich command line interface."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .database_admin import DatabaseSetupError, apply_migrations, diagnose_database
from .demo_data import demo_research_inputs, make_market_payload
from .dependencies import AgentDependencies
from .providers import InMemoryMarketDataProvider
from .routing import TaskExecutionPlan, TaskType, get_execution_plan
from .runner import run_research
from .runtime_config import (
    llm_is_configured,
    load_settings,
    paid_provider_names,
    update_local_setting,
)
from .service import (
    DatabaseUnavailableError,
    RunConfigurationError,
    RunOptions,
    TargetMarketDataUnavailableError,
    data_status,
    refresh_data,
    run_analysis,
)


app = typer.Typer(
    name="diagram-langgraph-pipeline",
    help="DB-first 多智能体股票研究命令行。",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
)
data_app = typer.Typer(help="检查或刷新数据库行情缓存。", add_completion=False)
app.add_typer(data_app, name="data")
stderr = Console(stderr=True)
stdout = Console()


@app.callback()
def root(ctx: typer.Context) -> None:
    """无参数且连接 TTY 时进入循环研究向导。"""
    if ctx.invoked_subcommand is not None:
        return
    if not sys.stdin.isatty():
        stdout.print(ctx.get_help())
        return
    _wizard()


@app.command("init")
def init_database(
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过迁移确认。"),
) -> None:
    """诊断连接并应用缺失的 PostgreSQL 迁移。"""
    settings = load_settings()
    dsn = settings.get("DATABASE_URL", "")
    if not dsn:
        if yes or not sys.stdin.isatty():
            _fail("缺少 DATABASE_URL；请在交互终端运行 init", 2)
        dsn = typer.prompt("PostgreSQL DATABASE_URL", hide_input=True)
    diagnostic = diagnose_database(dsn)
    if not diagnostic.ok and sys.stdin.isatty() and not yes:
        stderr.print(f"[yellow]{diagnostic.message}[/yellow]")
        dsn = typer.prompt("请输入可用的 DATABASE_URL", hide_input=True)
        diagnostic = diagnose_database(dsn)
    if not diagnostic.ok:
        _fail(f"{diagnostic.message}；当前配置 {diagnostic.configured_dsn}", 3)
    stderr.print(f"[green]{diagnostic.message}[/green]")
    if not yes and not typer.confirm("应用缺失迁移并更新本地连接配置？", default=False):
        raise typer.Exit(0)
    try:
        applied = apply_migrations(dsn)
        update_local_setting("DATABASE_URL", dsn)
    except DatabaseSetupError as exc:
        _fail(str(exc), 3)
    stderr.print(
        "[green]数据库已就绪[/green]；应用："
        + (", ".join(applied) if applied else "无（已是最新）")
    )


@app.command("run")
def run_command(
    ticker: Optional[str] = typer.Argument(
        None, help="需要个股数据的任务填写证券代码。"
    ),
    task: TaskType = typer.Option(
        TaskType.FULL, "--task", case_sensitive=False
    ),
    industry_name: Optional[str] = typer.Option(None, "--industry-name"),
    report_days: int = typer.Option(70, "--report-days"),
    technical_days: int = typer.Option(251, "--technical-days"),
    as_of: str = typer.Option(date.today().isoformat(), "--as-of"),
    benchmark: Optional[str] = typer.Option(None, "--benchmark"),
    sector_index: Optional[str] = typer.Option(None, "--sector-index"),
    horizon: str = typer.Option("medium", "--horizon"),
    llm: Optional[bool] = typer.Option(None, "--llm/--no-llm"),
    offline: bool = typer.Option(False, "--offline"),
    refresh: bool = typer.Option(False, "--refresh"),
    allow_paid: bool = typer.Option(False, "--allow-paid"),
    json_output: bool = typer.Option(False, "--json"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    """按所选任务运行一次研究。"""
    options = RunOptions(
        ticker=ticker, task_type=task, industry_name=industry_name,
        report_days=report_days, technical_days=technical_days,
        as_of=_parse_date_option(as_of), benchmark=benchmark, sector_index=sector_index,
        horizon=horizon, llm=llm, offline=offline, refresh=refresh,
        allow_paid=allow_paid, output=output,
    )
    settings = load_settings()
    configured_paid = paid_provider_names(settings)
    if configured_paid and not allow_paid and not offline:
        _fail(
            "检测到计量/付费 Provider（"
            + "、".join(configured_paid)
            + "）；非交互运行必须显式传入 --allow-paid",
            2,
        )
    plan = get_execution_plan(task)
    if not json_output:
        _print_task_plan(plan)
    try:
        state, summary = run_analysis(
            options, settings,
            event_callback=(
                _TaskProgressPrinter(plan) if not json_output else _quiet_event_printer
            ),
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(summary, ensure_ascii=False, default=str))
        return
    _print_summary(summary)
    stderr.print(f"[green]报告已保存：{summary['report_path']}[/green]")


@data_app.command("status")
def data_status_command(
    ticker: str,
    report_days: int = typer.Option(70, "--report-days"),
    technical_days: int = typer.Option(251, "--technical-days"),
    as_of: str = typer.Option(date.today().isoformat(), "--as-of"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """只读展示数据库覆盖和下一预计 Provider。"""
    try:
        result = data_status(
            ticker, report_days, technical_days, _parse_date_option(as_of), load_settings()
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, default=str))
    else:
        table = Table(title=f"{result['ticker']} 数据覆盖")
        table.add_column("项目")
        table.add_column("值")
        for key, value in result.items():
            if key != "ticker":
                table.add_row(key, str(value))
        stdout.print(table)


@data_app.command("refresh")
def data_refresh_command(
    ticker: str,
    report_days: int = typer.Option(70, "--report-days"),
    technical_days: int = typer.Option(251, "--technical-days"),
    as_of: str = typer.Option(date.today().isoformat(), "--as-of"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """绕过正缓存并显式补采 Yahoo 行情。"""
    try:
        result = refresh_data(
            RunOptions(
                ticker=ticker,
                report_days=report_days,
                technical_days=technical_days,
                as_of=_parse_date_option(as_of),
                refresh=True,
            ),
            load_settings(),
            event_callback=_event_printer if not json_output else _quiet_event_printer,
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, default=str))
    else:
        stdout.print(result)


@app.command("demo")
def demo() -> None:
    """运行原有、无需数据库和网络的确定性演示。"""
    payloads = {
        "DEMO": make_market_payload(20.0, 0.0010),
        "BENCH": make_market_payload(100.0, 0.0003),
        "SECTOR": make_market_payload(50.0, 0.0006),
    }
    state = run_research(
        {
            "ticker": "DEMO", "company_name": "示例公司", "industry_name": "示例行业",
            "as_of_date": "2026-07-21", "investment_horizon": "medium",
            "user_request": "完整研究", "benchmark_ticker": "BENCH",
            "sector_index_ticker": "SECTOR", "research_inputs": demo_research_inputs(),
            "retry_count": 0, "max_retries": 1,
        },
        AgentDependencies(market_data=InMemoryMarketDataProvider(payloads), llm=None),
    )
    typer.echo(state["final_markdown"])


def _wizard() -> None:
    settings = load_settings()
    while True:
        task_type = _prompt_task_type()
        plan = get_execution_plan(task_type)
        ticker = None
        if "ticker" in plan.required_inputs:
            ticker = typer.prompt("Ticker").strip().upper()
        industry_name = None
        if task_type is TaskType.INDUSTRY:
            industry_name = (
                typer.prompt("行业名称（留空从证券元数据推断）", default="").strip()
                or None
            )
        elif task_type is TaskType.FULL:
            industry_name = (
                typer.prompt("行业名称（留空从证券元数据推断）", default="").strip()
                or None
            )
        as_of = _prompt_date("截止日", date.today())
        report_days = _prompt_days("报告交易日", 70)
        if any(
            node in plan.enabled_nodes
            for node in ("stock_data_fetch", "index_analysis", "sector_technical")
        ):
            technical_days = _prompt_days("技术交易日", 251, minimum=report_days)
        else:
            technical_days = max(251, report_days)
        horizon = _prompt_horizon()
        benchmark = None
        sector = None
        if task_type in {TaskType.FULL, TaskType.MARKET}:
            benchmark = typer.prompt(
                "基准指数（留空自动推断）", default=""
            ).strip() or None
            sector = typer.prompt(
                "行业指数（留空表示不指定）", default=""
            ).strip() or None
        llm = typer.confirm("启用完整 D4F？", default=llm_is_configured(settings))
        paid = paid_provider_names(settings)
        allow_paid = False
        if paid:
            stderr.print("预计可能调用：" + "、".join(paid))
            allow_paid = typer.confirm("允许调用这些计量/付费 Provider？", default=False)
        _print_task_plan(plan)
        if not typer.confirm("按以上计划开始研究？", default=True):
            if typer.confirm("重新输入？", default=True):
                continue
            return
        try:
            state, summary = run_analysis(
                RunOptions(
                    ticker=ticker,
                    task_type=task_type,
                    industry_name=industry_name,
                    report_days=report_days,
                    technical_days=technical_days,
                    as_of=as_of,
                    benchmark=benchmark,
                    sector_index=sector,
                    horizon=horizon,
                    llm=llm,
                    allow_paid=allow_paid,
                ),
                settings, event_callback=_TaskProgressPrinter(plan),
            )
        except Exception as exc:
            stderr.print(f"[red]{exc}[/red]")
            if typer.confirm("重新输入？", default=True):
                continue
            return
        _print_summary(summary)
        while True:
            choice = typer.prompt(
                "下一步：summary/report/tokens/again/exit", default="summary"
            ).lower()
            if choice == "summary":
                _print_summary(summary)
            elif choice == "report":
                stdout.print(state["final_markdown"])
            elif choice == "tokens":
                _print_token_usage(summary)
            elif choice == "again":
                break
            elif choice == "exit":
                return
            else:
                stderr.print("请输入 summary、report、tokens、again 或 exit")


def _prompt_task_type() -> TaskType:
    labels = {
        "完整研究": TaskType.FULL,
        "行业研究": TaskType.INDUSTRY,
        "基本面研究": TaskType.FUNDAMENTAL,
        "技术面研究": TaskType.TECHNICAL,
        "市场研究": TaskType.MARKET,
    }
    choices = " / ".join(
        f"{label}({task_type.value})" for label, task_type in labels.items()
    )
    while True:
        value = typer.prompt(f"研究任务：{choices}", default=TaskType.FULL.value).strip()
        if value in labels:
            return labels[value]
        try:
            return TaskType(value.lower())
        except ValueError:
            stderr.print("[red]请输入 full、industry、fundamental、technical 或 market[/red]")


def _print_task_plan(plan: TaskExecutionPlan) -> None:
    table = Table(title="研究任务计划")
    table.add_column("项目")
    table.add_column("内容")
    table.add_row("task", plan.task_type.value)
    table.add_row("结论范围", plan.conclusion_scope)
    table.add_row("required", str(len(plan.required_nodes)))
    table.add_row("support", str(len(plan.support_nodes)))
    table.add_row("optional", str(len(plan.optional_nodes)))
    table.add_row("skipped", str(len(plan.skipped_nodes)))
    stdout.print(
        f"task={plan.task_type.value}  scope={plan.conclusion_scope}  "
        f"skipped={len(plan.skipped_nodes)}"
    )
    stdout.print(table)


class _TaskProgressPrinter:
    def __init__(self, plan: TaskExecutionPlan) -> None:
        self._enabled_nodes = set(plan.enabled_nodes)
        self._terminal_nodes: set[str] = set()
        self._total = len(plan.enabled_nodes)

    def __call__(self, event) -> None:
        if event.event_type != "node" or event.stage not in self._enabled_nodes:
            return
        if event.status in {"completed", "degraded", "failed"}:
            self._terminal_nodes.add(event.stage)
        reason = (
            f"  reason={event.message}"
            if event.status in {"degraded", "failed"}
            else ""
        )
        color = {
            "completed": "green",
            "degraded": "yellow",
            "failed": "red",
        }.get(event.status, "cyan")
        stderr.print(
            f"[{color}]{len(self._terminal_nodes)}/{self._total}[/{color}] "
            f"{event.stage}  {event.status}{reason}"
        )


def _prompt_days(label: str, default: int, minimum: int = 5) -> int:
    while True:
        value = typer.prompt(
            f"{label}（20/70/120/251/500 或 5–2000 自定义）",
            default=default, type=int,
        )
        if minimum <= value <= 2000:
            return value
        stderr.print(f"[red]请输入 {minimum}–2000[/red]")


def _prompt_horizon() -> str:
    while True:
        value = typer.prompt("投资期限 short/medium/long", default="medium").lower()
        if value in {"short", "medium", "long"}:
            return value
        stderr.print("[red]请输入 short、medium 或 long[/red]")


def _prompt_date(label: str, default: date) -> date:
    while True:
        raw = typer.prompt(label, default=default.isoformat())
        try:
            return date.fromisoformat(raw)
        except ValueError:
            stderr.print("[red]日期格式应为 YYYY-MM-DD[/red]")


def _parse_date_option(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter("日期格式应为 YYYY-MM-DD", param_hint="--as-of") from exc


def _event_printer(event) -> None:
    color = {"completed": "green", "degraded": "yellow", "failed": "red"}.get(event.status, "cyan")
    stderr.print(f"[{color}]{event.status:9}[/{color}] {event.stage}: {event.message}")


def _quiet_event_printer(event) -> None:
    if event.status in {"degraded", "failed"}:
        _event_printer(event)


def _print_summary(summary) -> None:
    decision = summary.get("decision", {})
    review = summary.get("review", {})
    conclusion = (
        f"decision={decision.get('action_bias', 'unknown')}"
        if decision or summary.get("task_type", "full") == "full"
        else f"scope={summary.get('conclusion_scope') or summary.get('task_type')}"
    )
    stdout.print(
        f"run_id={summary.get('run_id')}  ticker={summary.get('ticker')}  "
        f"{conclusion}  "
        f"review={'pass' if review.get('passed') else 'not-pass'}"
    )


def _print_token_usage(summary) -> None:
    usage = summary.get("d4f_token_usage", {})
    nodes = usage.get("nodes", {})
    if not nodes:
        stdout.print("本次运行未产生 D4F Token 用量（模型已关闭或没有成功调用）。")
        return
    table = Table(title="D4F Token 消耗")
    table.add_column("节点")
    table.add_column("状态")
    table.add_column("输入", justify="right")
    table.add_column("输出", justify="right")
    table.add_column("缓存", justify="right")
    table.add_column("输入估算", justify="right")
    table.add_column("偏差", justify="right")
    for node_name, item in sorted(nodes.items()):
        actual = int(item.get("prompt_tokens", 0) or 0)
        estimated = int(item.get("estimated_prompt_tokens", 0) or 0)
        deviation = (
            f"{(actual - estimated) / actual:+.1%}" if actual else "—"
        )
        table.add_row(
            node_name,
            str(item.get("status", "unknown")),
            f"{actual:,}",
            f"{int(item.get('completion_tokens', 0) or 0):,}",
            f"{int(item.get('cached_tokens', 0) or 0):,}",
            f"{estimated:,}",
            deviation,
        )
    stdout.print(table)
    stdout.print(
        "合计："
        f"输入 {int(usage.get('prompt_tokens', 0) or 0):,}，"
        f"输出 {int(usage.get('completion_tokens', 0) or 0):,}，"
        f"缓存 {int(usage.get('cached_tokens', 0) or 0):,}，"
        f"总计 {int(usage.get('total_tokens', 0) or 0):,} Token；"
        f"输入估算 {int(usage.get('estimated_prompt_tokens', 0) or 0):,}。"
    )


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, RunConfigurationError):
        _fail(str(exc), 2)
    if isinstance(exc, DatabaseUnavailableError):
        _fail(str(exc), 3)
    if isinstance(exc, TargetMarketDataUnavailableError):
        _fail(str(exc), 4)
    _fail(f"框架运行失败：{type(exc).__name__}: {exc}", 5)


def _fail(message: str, code: int) -> None:
    stderr.print(f"[red]{message}[/red]")
    raise typer.Exit(code)


def main() -> None:
    app(prog_name="diagram-langgraph-pipeline")
