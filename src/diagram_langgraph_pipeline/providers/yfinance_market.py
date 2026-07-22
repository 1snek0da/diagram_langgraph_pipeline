"""Optional Yahoo Finance adapter for live OHLCV and current valuation data."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class YFinanceMarketDataProvider:
    def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance to use YFinanceMarketDataProvider") from exc

        instrument = yf.Ticker(ticker)
        frame = instrument.history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
        bars: list[dict[str, Any]] = []
        for index, row in frame.iterrows():
            bars.append(
                {
                    "trade_date": index.date().isoformat(),
                    "open": _number(row.get("Open")),
                    "high": _number(row.get("High")),
                    "low": _number(row.get("Low")),
                    "close": _number(row.get("Close")),
                    "adj_close": _number(row.get("Adj Close", row.get("Close"))),
                    "volume": _number(row.get("Volume")),
                }
            )

        info = instrument.info or {}
        valuation = {
            "trade_date": end_date.isoformat(),
            "pe_ttm": _number(info.get("trailingPE")),
            "pb": _number(info.get("priceToBook")),
            "ps_ttm": _number(info.get("priceToSalesTrailing12Months")),
            "market_cap": _number(info.get("marketCap")),
        }
        return {
            "bars": bars,
            "valuations": [valuation],
            "source": "yfinance",
            "metadata": {"currency": info.get("currency")},
        }


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None
