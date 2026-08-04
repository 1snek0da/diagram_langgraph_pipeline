"""Optional Yahoo Finance adapter for live OHLCV and current valuation data."""

from __future__ import annotations

from datetime import date, timedelta
import os
from typing import Any


class YFinanceMarketDataProvider:
    def __init__(
        self,
        cache_dir: str | None = None,
        *,
        intraday_interval: str = "1m",
    ) -> None:
        self.cache_dir = cache_dir or os.getenv("YFINANCE_CACHE_DIR")
        self.intraday_interval = intraday_interval

    def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "Install yfinance to use YFinanceMarketDataProvider"
            ) from exc

        if self.cache_dir:
            yf.set_tz_cache_location(self.cache_dir)

        instrument = yf.Ticker(ticker)
        frame = instrument.history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
        bars = _daily_rows(frame)

        minute_bars: list[dict[str, Any]] = []
        intraday_note = f"Yahoo {self.intraday_interval} K线已请求"
        try:
            if self.intraday_interval == "1m":
                intraday = instrument.history(
                    period="1d", interval="1m", auto_adjust=False
                )
            else:
                intraday = instrument.history(
                    start=start_date.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    interval=self.intraday_interval,
                    auto_adjust=False,
                )
            for index, row in intraday.iterrows():
                minute_bars.append(
                    {
                        "trade_date": index.isoformat(),
                        "open": _number(row.get("Open")),
                        "high": _number(row.get("High")),
                        "low": _number(row.get("Low")),
                        "close": _number(row.get("Close")),
                        "adj_close": _number(row.get("Close")),
                        "volume": _number(row.get("Volume")),
                    }
                )
        except Exception as exc:  # pragma: no cover - provider/network dependent
            intraday_note = (
                f"Yahoo {self.intraday_interval} K线请求失败: {type(exc).__name__}"
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
            "minute_bars": minute_bars,
            "valuations": [valuation],
            "source": "yfinance",
            "metadata": {
                "currency": info.get("currency"),
                "intraday_note": intraday_note,
                "intraday_interval": self.intraday_interval,
                "intraday_bar_count": len(minute_bars),
            },
        }

    def fetch_daily(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Fetch daily history only, avoiding an unnecessary intraday request."""

        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "Install yfinance to use YFinanceMarketDataProvider"
            ) from exc
        if self.cache_dir:
            yf.set_tz_cache_location(self.cache_dir)
        frame = yf.Ticker(ticker).history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
        return _daily_rows(frame)


def _daily_rows(frame: Any) -> list[dict[str, Any]]:
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
    return bars


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None
