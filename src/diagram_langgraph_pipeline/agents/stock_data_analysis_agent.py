"""Stock market-data analysis node."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..analysis.market_metrics import analyze_market_payload
from ..analysis.technical_scoring import score_trend_system
from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    market_data = state.get("stock_market_data", {})
    analysis = analyze_market_payload(
        market_data.get("stock", {}),
        benchmark_payload=market_data.get("benchmark"),
        sector_payload=market_data.get("sector"),
    )
    analysis["ticker"] = state["ticker"]
    analysis["trend_scoring"] = score_trend_system(
        market_data.get("stock", {}).get("bars", [])
    )
    stock_payload = market_data.get("stock", {})
    bars = stock_payload.get("bars", [])
    technical_bars = stock_payload.get("technical_bars", bars)
    analysis["analysis_window"] = f"latest_{len(bars)}_trading_days"
    analysis["technical_analysis_window"] = (
        f"latest_{len(technical_bars)}_trading_days"
    )
    if bars:
        first_date = str(bars[0].get("trade_date", ""))
        last_date = str(bars[-1].get("trade_date", ""))
        provider = str(stock_payload.get("source", "unknown"))
        analysis["evidence"] = [
            {
                "evidence_id": str(uuid4()),
                "source_id": f"{provider}:{state['ticker']}:{first_date}:{last_date}",
                "evidence_type": "market_data",
                "claim_text": (
                    f"{state['ticker']} 日线行情覆盖 {first_date} 至 {last_date}，"
                    f"共 {len(bars)} 个交易日。"
                ),
                "metric_key": "daily_ohlcv",
                "extraction_method": "api",
                "confidence_score": 0.95,
                "metadata": {
                    "provider": provider,
                    "ticker": state["ticker"],
                    "first_trade_date": first_date,
                    "last_trade_date": last_date,
                    "bar_count": len(bars),
                },
            }
        ]
    return {"stock_market_data_analysis": analysis}
