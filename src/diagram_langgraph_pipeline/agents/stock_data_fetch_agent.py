"""Stock OHLCV, valuation, and comparison-index fetch node."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..dependencies import AgentDependencies
from ..routing import get_execution_plan


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    end_date = _parse_date(state.get("as_of_date"))
    history_days = max(1, min(int(state.get("market_history_days", 550)), 3650))
    fallback_days = max(
        history_days,
        min(int(state.get("market_history_fallback_days", history_days)), 3650),
    )
    configured_trading_days = int(state.get("daily_trading_days", 0) or 0)
    trading_days = max(1, configured_trading_days) if configured_trading_days else 0
    configured_technical_days = int(state.get("technical_trading_days", 0) or 0)
    technical_days = (
        max(trading_days, configured_technical_days)
        if configured_technical_days
        else trading_days
    )
    technical_history_days = max(
        fallback_days,
        min(int(state.get("technical_history_days", 550)), 3650),
    )
    start_date = end_date - timedelta(days=history_days)
    ticker = state["ticker"]
    benchmark_ticker = state.get("benchmark_ticker", "000300.SS")
    sector_ticker = state.get("sector_index_ticker", "")
    enabled_nodes = set(
        get_execution_plan(state.get("task_type", "full")).enabled_nodes
    )

    stock = _fetch_with_coverage(
        deps,
        ticker,
        start_date,
        end_date,
        fallback_days,
        trading_days,
        technical_days,
        technical_history_days,
    )
    benchmark = (
        _fetch_with_coverage(
            deps,
            benchmark_ticker,
            start_date,
            end_date,
            fallback_days,
            trading_days,
            technical_days,
            technical_history_days,
        )
        if benchmark_ticker and "index_analysis" in enabled_nodes
        else None
    )
    sector = (
        _fetch_with_coverage(
            deps,
            sector_ticker,
            start_date,
            end_date,
            fallback_days,
            trading_days,
            technical_days,
            technical_history_days,
        )
        if sector_ticker and "sector_technical" in enabled_nodes
        else None
    )
    save_market_data = getattr(deps.repository, "save_market_data", None)
    persistence_managed = bool(
        stock.get("metadata", {}).get("persistence_managed")
    )
    if callable(save_market_data) and not persistence_managed:
        save_market_data(str(state.get("run_id", "")), ticker, stock)
        if benchmark_ticker and benchmark:
            save_market_data(
                str(state.get("run_id", "")), benchmark_ticker, benchmark
            )
        if sector_ticker and sector:
            save_market_data(str(state.get("run_id", "")), sector_ticker, sector)
    deps.repository.record_provider_fetch(
        str(state.get("run_id", "")),
        str(stock.get("source", "unknown")),
        "market_data",
        {
            "ticker": ticker,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "technical_start_date": (
                end_date - timedelta(days=technical_history_days)
            ).isoformat(),
        },
        {
            "bar_count": len(stock.get("bars", [])),
            "minute_bar_count": len(stock.get("minute_bars", [])),
            "valuation_count": len(stock.get("valuations", [])),
            "requested_trading_days": trading_days or None,
            "technical_requested_trading_days": technical_days or None,
            "technical_bar_count": len(stock.get("technical_bars", [])),
            "cache_status": stock.get("metadata", {}).get("cache_status"),
            "database_bar_count": stock.get("metadata", {}).get(
                "database_bar_count"
            ),
            "api_bar_count": stock.get("metadata", {}).get("api_bar_count"),
            "intraday_interval": state.get("intraday_interval"),
            "intraday_target_bars_per_day": state.get(
                "intraday_target_bars_per_day"
            ),
            "intraday_actual_bars_per_day": _bars_per_day(
                stock.get("minute_bars", [])
            ),
        },
    )
    return {
        "stock_market_data": {
            "ticker": ticker,
            "stock": stock,
            "benchmark_ticker": benchmark_ticker,
            "benchmark": benchmark,
            "sector_index_ticker": sector_ticker,
            "sector": sector,
            "data_source": stock.get("source", "unknown"),
        }
    }


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value))
    return date.today()


def _fetch_with_coverage(
    deps: AgentDependencies,
    ticker: str,
    start_date: date,
    end_date: date,
    fallback_days: int,
    trading_days: int,
    technical_days: int,
    technical_history_days: int,
) -> dict[str, Any]:
    payload = deps.market_data.fetch(ticker, start_date, end_date)
    if trading_days and len(payload.get("bars", [])) < trading_days:
        fallback_start = end_date - timedelta(days=fallback_days)
        if fallback_start < start_date:
            payload = deps.market_data.fetch(ticker, fallback_start, end_date)
    raw_daily_bars = list(payload.get("bars", []))
    technical_bars = raw_daily_bars
    if technical_days and len(technical_bars) < technical_days:
        technical_start = end_date - timedelta(days=technical_history_days)
        fetch_daily = getattr(deps.market_data, "fetch_daily", None)
        if callable(fetch_daily):
            technical_bars = list(fetch_daily(ticker, technical_start, end_date))
        else:
            technical_payload = deps.market_data.fetch(
                ticker, technical_start, end_date
            )
            technical_bars = list(technical_payload.get("bars", []))
    if technical_days:
        technical_bars = technical_bars[-technical_days:]

    if trading_days or technical_days:
        payload = dict(payload)
        payload["technical_bars"] = technical_bars
    if trading_days:
        payload["bars"] = raw_daily_bars[-trading_days:]
        covered_dates = {
            str(item.get("trade_date", ""))[:10] for item in payload["bars"]
        }
        payload["minute_bars"] = [
            item
            for item in payload.get("minute_bars", [])
            if str(item.get("trade_date", ""))[:10] in covered_dates
        ]
        metadata = dict(payload.get("metadata", {}))
        metadata.update(
            {
                "requested_trading_days": trading_days,
                "actual_trading_days": len(payload["bars"]),
                "daily_coverage_complete": len(payload["bars"]) == trading_days,
                "technical_requested_trading_days": technical_days,
                "technical_actual_trading_days": len(technical_bars),
                "technical_coverage_complete": len(technical_bars)
                == technical_days,
            }
        )
        payload["metadata"] = metadata
    return payload


def _bars_per_day(bars: list[dict[str, Any]]) -> float:
    days = {str(item.get("trade_date", ""))[:10] for item in bars}
    days.discard("")
    return round(len(bars) / len(days), 2) if days else 0.0
