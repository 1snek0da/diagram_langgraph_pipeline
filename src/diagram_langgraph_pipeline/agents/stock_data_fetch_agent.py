"""Stock OHLCV, valuation, and comparison-index fetch node."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    end_date = _parse_date(state.get("as_of_date"))
    start_date = end_date - timedelta(days=550)
    ticker = state["ticker"]
    benchmark_ticker = state.get("benchmark_ticker", "000300.SS")
    sector_ticker = state.get("sector_index_ticker", "")

    stock = deps.market_data.fetch(ticker, start_date, end_date)
    benchmark = deps.market_data.fetch(benchmark_ticker, start_date, end_date) if benchmark_ticker else None
    sector = deps.market_data.fetch(sector_ticker, start_date, end_date) if sector_ticker else None
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
