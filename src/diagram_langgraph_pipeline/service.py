"""Application service behind the interactive and scriptable CLI."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .dependencies import AgentDependencies
from .events import RecordingEventSink
from .providers import (
    DatabaseFirstMarketDataProvider,
    PostgresAnalysisRepository,
    YFinanceMarketDataProvider,
    YahooResearchAdapter,
    build_optional_llm_provider,
    build_research_provider,
)
from .providers.http_transport import HttpPolicy, ResilientHttpTransport
from .providers.sec_edgar import SecEdgarAdapter
from .runner import run_research
from .routing import TaskType, get_execution_plan
from .runtime_config import PROJECT_ROOT, llm_is_configured


class RunConfigurationError(ValueError):
    pass


class DatabaseUnavailableError(RuntimeError):
    pass


class TargetMarketDataUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunOptions:
    ticker: str | None = None
    task_type: TaskType = TaskType.FULL
    industry_name: str | None = None
    report_days: int = 70
    technical_days: int = 251
    as_of: date = field(default_factory=date.today)
    benchmark: str | None = None
    sector_index: str | None = None
    horizon: str = "medium"
    llm: bool | None = None
    offline: bool = False
    refresh: bool = False
    allow_paid: bool = False
    output: Path | None = None


SECTOR_ETFS = {
    "technology": "XLK", "financial services": "XLF", "healthcare": "XLV",
    "consumer cyclical": "XLY", "consumer defensive": "XLP",
    "communication services": "XLC", "industrials": "XLI", "energy": "XLE",
    "basic materials": "XLB", "real estate": "XLRE", "utilities": "XLU",
}


def validate_options(options: RunOptions) -> None:
    plan = get_execution_plan(options.task_type)
    if "ticker" in plan.required_inputs and not (options.ticker or "").strip():
        raise RunConfigurationError("Ticker 不能为空")
    if "industry_name" in plan.required_inputs and not (options.industry_name or "").strip():
        if plan.task_type is not TaskType.FULL or not (options.ticker or "").strip():
            raise RunConfigurationError("行业名称不能为空")
    if not 5 <= options.report_days <= 2000:
        raise RunConfigurationError("报告交易日必须在 5–2000 之间")
    if not 5 <= options.technical_days <= 2000:
        raise RunConfigurationError("技术交易日必须在 5–2000 之间")
    if options.technical_days < options.report_days:
        raise RunConfigurationError("技术交易日不得小于报告交易日")
    if options.horizon not in {"short", "medium", "long"}:
        raise RunConfigurationError("投资期限只能是 short、medium 或 long")
    if options.offline and options.refresh:
        raise RunConfigurationError("--offline 与 --refresh 互斥")


def run_analysis(
    options: RunOptions,
    settings: Mapping[str, str],
    *,
    event_callback=None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_options(options)
    plan = get_execution_plan(options.task_type)
    dsn = settings.get("DATABASE_URL", "")
    if not dsn:
        raise RunConfigurationError("缺少 DATABASE_URL，请先运行 init")
    try:
        repository = PostgresAnalysisRepository(dsn)
        health = repository.check_health()
    except Exception as exc:
        raise DatabaseUnavailableError(f"数据库不可用：{type(exc).__name__}") from exc
    if not health.get("cache_schema_ready"):
        raise RunConfigurationError("数据库尚未应用 003 迁移，请先运行 init")

    events = RecordingEventSink(event_callback)
    ticker = (options.ticker or "").strip().upper()
    metadata: Mapping[str, Any] = {}
    if "stock_data_fetch" in plan.enabled_nodes:
        metadata = repository.load_security(ticker) or {}
    if "stock_data_fetch" in plan.enabled_nodes and not metadata and not options.offline:
        try:
            metadata = YahooResearchAdapter(settings.get("YFINANCE_CACHE_DIR")).resolve_security(ticker)
            repository.upsert_security_metadata(dict(metadata))
        except Exception:
            metadata = {}
    if "stock_data_fetch" in plan.enabled_nodes:
        metadata = metadata or {
            "ticker": ticker, "company_name": ticker, "market": "UNKNOWN",
            "exchange": "UNKNOWN", "industry_name": "Unknown", "sector": None,
        }
    external_ids = dict(metadata.get("external_ids") or {})
    if (
        "stock_data_fetch" in plan.enabled_nodes
        and ticker
        and not options.offline
        and "." not in ticker
        and not ticker.startswith("^")
        and not external_ids.get("cik")
        and "@" in settings.get("SEC_USER_AGENT", "")
    ):
        try:
            external_ids["cik"] = SecEdgarAdapter(
                user_agent=settings["SEC_USER_AGENT"],
                client=ResilientHttpTransport(HttpPolicy(max_attempts=2)),
            ).resolve_cik(ticker)
            external_ids = {key: value for key, value in external_ids.items() if value}
            metadata = {**metadata, "external_ids": external_ids}
            repository.upsert_security_metadata(metadata)
        except Exception:
            pass
    if "stock_data_fetch" in plan.enabled_nodes:
        benchmark, sector = infer_comparisons(
            ticker,
            metadata,
            options.benchmark,
            options.sector_index,
        )
    else:
        benchmark = options.benchmark or (
            "000300.SS" if plan.task_type is TaskType.MARKET else None
        )
        sector = options.sector_index
    market_provider = DatabaseFirstMarketDataProvider(
        YFinanceMarketDataProvider(
            settings.get("YFINANCE_CACHE_DIR"), intraday_interval="60m"
        ),
        repository,
        report_days=options.report_days,
        technical_days=options.technical_days,
        intraday_interval="60m",
        offline=options.offline,
        refresh=options.refresh,
        events=events,
    )
    natural_days = min(3650, 2 * options.technical_days + 30)
    preview: Mapping[str, Any] = {
        "bars": [],
        "minute_bars": [],
        "valuations": [],
        "metadata": {},
    }
    research_start = options.as_of.isoformat()
    if "stock_data_fetch" in plan.enabled_nodes:
        preview = market_provider.fetch(
            ticker, options.as_of - timedelta(days=natural_days), options.as_of
        )
        preview_bars = list(preview.get("bars", []))
        if not preview_bars:
            raise TargetMarketDataUnavailableError(f"{ticker} 没有可用目标行情")
        report_bars = preview_bars[-options.report_days :]
        research_start = str(report_bars[0]["trade_date"])[:10]
    llm_enabled = llm_is_configured(settings) if options.llm is None else options.llm
    if llm_enabled and not llm_is_configured(settings):
        raise RunConfigurationError("已启用 D4F，但缺少模型 API Key")
    research = build_research_provider(
        settings,
        cache=repository,
        events=events,
        offline=options.offline,
        refresh=options.refresh,
        allow_paid=options.allow_paid,
        network_enabled=True,
    )
    state = run_research(
        {
            "task_type": plan.task_type.value,
            "ticker": ticker,
            "company_name": metadata.get("company_name") or (ticker if ticker else ""),
            "industry_name": (
                (options.industry_name or "").strip()
                or str(metadata.get("industry_name") or "Unknown")
            ),
            "company_cik": external_ids.get("cik", ""),
            "as_of_date": options.as_of.isoformat(),
            "investment_horizon": options.horizon,
            "user_request": (
                f"研究任务 {plan.task_type.value}："
                f"{ticker or (options.industry_name or plan.conclusion_scope)}；"
                f"报告窗口 {options.report_days} 个交易日"
            ),
            "benchmark_ticker": benchmark or "",
            "sector_index_ticker": sector or "",
            "run_profile": "d4f_70d",
            "daily_trading_days": options.report_days,
            "technical_trading_days": options.technical_days,
            "market_history_days": natural_days,
            "market_history_fallback_days": natural_days,
            "technical_history_days": natural_days,
            "research_window_start": research_start,
            "intraday_interval": "60m",
            "intraday_target_bars_per_day": 15,
            "news_limit": 36,
            "research_inputs": {},
            "retry_count": 0,
            "max_retries": 1,
        },
        AgentDependencies(
            market_data=market_provider,
            research=research,
            repository=repository,
            llm=build_optional_llm_provider(settings, enabled=llm_enabled),
            events=events,
        ),
    )
    acquisition = acquisition_summary(
        events.snapshot(), options, preview, research_start, options.allow_paid, state
    )
    state["data_acquisition_summary"] = acquisition
    state["final_markdown"] = str(state.get("final_markdown", "")) + render_acquisition(acquisition)
    repository.save_final_report(str(state["run_id"]), state["final_markdown"])
    report_path = _write_report(state, options.output)
    repository.update_report_path(str(state["run_id"]), str(report_path))
    return state, result_summary(state, acquisition, report_path)


def data_status(
    ticker: str,
    report_days: int,
    technical_days: int,
    as_of: date,
    settings: Mapping[str, str],
) -> dict[str, Any]:
    validate_options(
        RunOptions(
            ticker=ticker,
            report_days=report_days,
            technical_days=technical_days,
            as_of=as_of,
        )
    )
    dsn = settings.get("DATABASE_URL", "")
    if not dsn:
        raise RunConfigurationError("缺少 DATABASE_URL")
    try:
        repository = PostgresAnalysisRepository(dsn)
        repository.check_health()
        payload = repository.load_market_data(
            ticker.upper(), as_of - timedelta(days=min(3650, 2 * technical_days + 30)),
            as_of, intraday_interval="60m"
        )
        research_inventory = repository.load_research_cache_inventory(
            ticker.upper(), as_of
        )
    except Exception as exc:
        raise DatabaseUnavailableError(f"数据库不可用：{type(exc).__name__}") from exc
    bars = payload.get("bars", [])
    latest = str(bars[-1].get("trade_date"))[:10] if bars else None
    stale = True
    if latest:
        stale = (as_of - date.fromisoformat(latest)).days > 7
    return {
        "ticker": ticker.upper(), "report_days": report_days,
        "technical_days": technical_days, "database_daily_bars": len(bars),
        "database_intraday_bars": len(payload.get("minute_bars", [])),
        "database_valuations": len(payload.get("valuations", [])),
        "latest_daily_bar": latest,
        "stale": stale,
        "research_cache": research_inventory,
        "status": "complete" if len(bars) >= technical_days and not stale else "partial" if bars else "missing",
        "next_provider": None if len(bars) >= technical_days and not stale else "Yahoo Finance",
        "missing_daily_bars": max(0, technical_days - len(bars)),
    }


def refresh_data(options: RunOptions, settings: Mapping[str, str], *, event_callback=None) -> dict[str, Any]:
    validate_options(options)
    if options.offline:
        raise RunConfigurationError("refresh 不支持离线模式")
    repository = PostgresAnalysisRepository(settings.get("DATABASE_URL", ""))
    try:
        repository.check_health()
    except Exception as exc:
        raise DatabaseUnavailableError(f"数据库不可用：{type(exc).__name__}") from exc
    events = RecordingEventSink(event_callback)
    provider = DatabaseFirstMarketDataProvider(
        YFinanceMarketDataProvider(settings.get("YFINANCE_CACHE_DIR"), intraday_interval="60m"),
        repository, report_days=options.report_days, technical_days=options.technical_days,
        intraday_interval="60m", refresh=True, events=events,
    )
    ticker = (options.ticker or "").upper()
    payload = provider.fetch(
        ticker,
        options.as_of - timedelta(days=min(3650, 2 * options.technical_days + 30)),
        options.as_of,
    )
    if not payload.get("bars"):
        raise TargetMarketDataUnavailableError(f"{ticker} 没有可用目标行情")
    return {
        "ticker": ticker,
        "daily_bars": len(payload.get("bars", [])),
        "intraday_bars": len(payload.get("minute_bars", [])),
        "api_added": payload.get("metadata", {}).get("api_bar_count", 0),
        "cache_status": payload.get("metadata", {}).get("cache_status"),
    }


def infer_comparisons(
    ticker: str, metadata: Mapping[str, Any], benchmark: str | None, sector: str | None
) -> tuple[str | None, str | None]:
    upper = ticker.upper()
    if upper.endswith((".SS", ".SZ")):
        inferred_benchmark, inferred_sector = "000300.SS", None
    elif upper.endswith(".HK"):
        inferred_benchmark, inferred_sector = "^HSI", None
    elif "." not in upper and not upper.startswith("^"):
        key = str(metadata.get("sector") or metadata.get("industry_name") or "").lower()
        sector_ticker = next((value for name, value in SECTOR_ETFS.items() if name in key), None)
        inferred_benchmark, inferred_sector = "^GSPC", sector_ticker
    else:
        inferred_benchmark, inferred_sector = None, None
    return (
        inferred_benchmark if benchmark is None else benchmark,
        inferred_sector if sector is None else sector,
    )


def acquisition_summary(events, options, preview, research_start, allow_paid, state):
    providers = [event for event in events if event.event_type == "provider"]
    nodes = [event for event in events if event.event_type == "node"]
    statuses = Counter(event.metadata.get("cache_status") or event.status for event in providers)
    latest_nodes = {}
    for event in nodes:
        latest_nodes[event.stage] = event.status
    minute = preview.get("minute_bars", [])
    days = len({str(item.get("trade_date", ""))[:10] for item in minute}) or 1
    news_evidence = [
        item for item in state.get("sentiment_result", {}).get("evidence", [])
        if item.get("evidence_type") == "news"
    ]
    news_dates = sorted(
        str(item.get("published_at", ""))[:10]
        for item in news_evidence if item.get("published_at")
    )
    return {
        "report_trading_days": options.report_days,
        "technical_trading_days": options.technical_days,
        "actual_report_start": research_start,
        "daily_bars": min(options.technical_days, len(preview.get("bars", []))),
        "intraday_interval": "60m",
        "intraday_target_bars_per_day": 15,
        "intraday_actual_bars_per_day": round(len(minute) / days, 2),
        "provider_status_counts": dict(statuses),
        "provider_accesses": [
            {
                "stage": event.stage,
                "status": event.status,
                "cache_status": event.metadata.get("cache_status"),
                "database_rows": event.metadata.get("database_bar_count"),
                "api_rows": event.metadata.get("api_bar_count"),
            }
            for event in providers if event.status != "started"
        ],
        "node_statuses": latest_nodes,
        "node_status_counts": dict(Counter(latest_nodes.values())),
        "d4f_nodes_with_output": len(state.get("llm_node_results", {})),
        "news_count": len(news_evidence),
        "news_span": [news_dates[0], news_dates[-1]] if news_dates else [],
        "paid_providers_authorized": allow_paid,
        "degradations": [event.message for event in providers if event.status in {"degraded", "failed"}],
    }


def render_acquisition(summary: Mapping[str, Any]) -> str:
    return (
        "\n\n## 数据获取摘要\n\n"
        f"- 报告/技术窗口：{summary['report_trading_days']} / {summary['technical_trading_days']} 个交易日\n"
        f"- 实际报告起始日：{summary['actual_report_start']}\n"
        f"- 盘中目标/实际：15 / {summary['intraday_actual_bars_per_day']} 根/交易日（60m，不插值）\n"
        f"- 新闻实际数量/跨度：{summary['news_count']} 条 / {summary['news_span'] or '无可用新闻'}\n"
        f"- 缓存与接口状态：`{json.dumps(summary['provider_status_counts'], ensure_ascii=False)}`\n"
        f"- 节点状态：`{json.dumps(summary['node_status_counts'], ensure_ascii=False)}`；D4F 节点输出 {summary['d4f_nodes_with_output']} 个\n"
        f"- 付费或计量 Provider 授权：{'是' if summary['paid_providers_authorized'] else '否'}\n"
    )


def result_summary(state: Mapping[str, Any], acquisition, report_path: Path) -> dict[str, Any]:
    node_usage = {
        str(node_name): {
            "status": item.get("status", "unknown"),
            "model": item.get("model"),
            "prompt_tokens": int(item.get("usage", {}).get("prompt_tokens", 0) or 0),
            "completion_tokens": int(item.get("usage", {}).get("completion_tokens", 0) or 0),
            "cached_tokens": int(item.get("usage", {}).get("cached_tokens", 0) or 0),
            "estimated_prompt_tokens": int(
                item.get("projection_manifest", {}).get("estimated_prompt_tokens", 0) or 0
            ),
        }
        for node_name, item in state.get("llm_node_results", {}).items()
    }
    usages = list(node_usage.values())
    prompt_tokens = sum(item["prompt_tokens"] for item in usages)
    completion_tokens = sum(item["completion_tokens"] for item in usages)
    return {
        "run_id": state.get("run_id"), "ticker": state.get("ticker"),
        "task_type": state.get("task_type", "full"),
        "enabled_nodes": [
            *state.get("required_nodes", []),
            *state.get("support_nodes", []),
            *state.get("optional_nodes", []),
        ],
        "skipped_nodes": state.get("skipped_nodes", []),
        "completed_nodes": state.get("completed_nodes", []),
        "failed_nodes": state.get("failed_nodes", []),
        "conclusion_scope": state.get("conclusion_scope"),
        "coverage": acquisition, "provider_calls": acquisition.get("provider_status_counts", {}),
        "d4f_token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_tokens": sum(item["cached_tokens"] for item in usages),
            "estimated_prompt_tokens": sum(
                item["estimated_prompt_tokens"] for item in usages
            ),
            "total_tokens": prompt_tokens + completion_tokens,
            "nodes": node_usage,
        },
        "decision": state.get("decision_result", {}), "review": state.get("review_result", {}),
        "report_path": str(report_path),
    }


def _write_report(state: Mapping[str, Any], requested: Path | None) -> Path:
    ticker = re.sub(
        r"[^A-Za-z0-9._^-]+",
        "_",
        str(state.get("ticker") or state.get("task_type") or "research"),
    )
    target = requested or PROJECT_ROOT / "outputs" / (
        f"final_report_{ticker}_{state['as_of_date']}_{str(state['run_id'])[:8]}.md"
    )
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(state.get("final_markdown", "")), encoding="utf-8")
    return target
