"""Fetch 70 trading days of Apple data and run the complete D4F graph."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import yfinance as yf

from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import (
    PostgresAnalysisRepository,
    build_research_provider,
)
from diagram_langgraph_pipeline.providers.volcengine_llm import (
    VolcengineChatClient,
    VolcengineLLMConfig,
)
from diagram_langgraph_pipeline.providers.yfinance_market import (
    YFinanceMarketDataProvider,
)
from diagram_langgraph_pipeline.runner import run_research


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = _load_settings(ROOT / ".env.local")
    cache_dir = ROOT / settings.get("YFINANCE_CACHE_DIR", ".local/yfinance-cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))

    as_of_date = date.today()
    instrument = yf.Ticker("AAPL")
    info = instrument.info or {}
    start_date = _trading_window_start(instrument, as_of_date, trading_days=70)
    news = _recent_news(instrument, start_date, as_of_date, limit=36)
    research_inputs = _research_inputs(info, news, start_date, as_of_date)

    llm = VolcengineChatClient(
        VolcengineLLMConfig(
            api_key=settings["VOLCENGINE_LLM_API_KEY"],
            base_url=settings["VOLCENGINE_LLM_BASE_URL"],
            model=settings["VOLCENGINE_LLM_MODEL"],
            timeout_seconds=float(
                settings.get("VOLCENGINE_LLM_TIMEOUT_SECONDS", "120")
            ),
            max_tokens=int(settings.get("VOLCENGINE_LLM_MAX_TOKENS", "1200")),
            temperature=float(settings.get("VOLCENGINE_LLM_TEMPERATURE", "0.1")),
            disable_thinking=True,
            json_mode=True,
        )
    )
    repository = PostgresAnalysisRepository(settings["DATABASE_URL"])
    result = run_research(
        {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "company_cik": "0000320193",
            "industry_name": info.get("industry") or "Consumer Electronics",
            "as_of_date": as_of_date.isoformat(),
            "investment_horizon": "medium",
            "user_request": (
                "Fetch Apple information covering the latest 70 trading days and run "
                "the complete traceable D4F-assisted research workflow."
            ),
            "benchmark_ticker": "^GSPC",
            "sector_index_ticker": "XLK",
            "run_profile": "d4f_70d",
            "research_inputs": research_inputs,
            "retry_count": 0,
            "max_retries": 0,
            "market": "US",
            "exchange": info.get("exchange") or "NASDAQ",
        },
        AgentDependencies(
            market_data=YFinanceMarketDataProvider(
                str(cache_dir), intraday_interval="60m"
            ),
            research=build_research_provider(settings),
            repository=repository,
            llm=llm,
        ),
    )

    output_dir = ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / (
        f"final_report_AAPL_{as_of_date}_{str(result['run_id'])[:8]}.md"
    )
    report_path.write_text(result["final_markdown"], encoding="utf-8", newline="\n")
    database_counts = _database_counts(settings["DATABASE_URL"], str(result["run_id"]))
    market = result.get("stock_market_data_analysis", {})
    summary = {
        "run_id": result["run_id"],
        "ticker": "AAPL",
        "requested_window": [start_date.isoformat(), as_of_date.isoformat()],
        "market_bar_count": market.get("data_coverage", {}).get("bar_count"),
        "technical_bar_count": market.get("data_coverage", {}).get(
            "technical_bar_count"
        ),
        "news_count": len(news),
        "daily_trading_days_requested": 70,
        "intraday_interval": "60m",
        "latest_close": market.get("latest_close"),
        "return_5d": market.get("return_5d"),
        "return_20d": market.get("return_20d"),
        "decision": result.get("decision_result", {}).get("action_bias"),
        "confidence": result.get("decision_result", {}).get("confidence_score"),
        "review_passed": result.get("review_result", {}).get("passed"),
        "llm_nodes": _llm_summary(result.get("llm_node_results", {})),
        "database": database_counts,
        "report_path": str(report_path),
        "report_bytes": report_path.stat().st_size,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def _load_settings(path: Path) -> dict[str, str]:
    settings = dict(os.environ)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            settings.setdefault(key, value)
    required = {
        "DATABASE_URL",
        "VOLCENGINE_LLM_API_KEY",
        "VOLCENGINE_LLM_BASE_URL",
        "VOLCENGINE_LLM_MODEL",
    }
    missing = [key for key in sorted(required) if not settings.get(key)]
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)}")
    return settings


def _recent_news(
    instrument: yf.Ticker, start_date: date, end_date: date, *, limit: int = 36
) -> list[dict[str, Any]]:
    try:
        raw_items = instrument.get_news(count=100, tab="news") or []
    except (AttributeError, TypeError):
        raw_items = instrument.news or []
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(
        end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    normalized: list[dict[str, Any]] = []
    for raw in raw_items:
        content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
        title = str(content.get("title") or "").strip()
        published_at = _published_at(content)
        if not title or published_at is None or not start <= published_at < end:
            continue
        provider = content.get("provider")
        publisher = (
            provider.get("displayName")
            if isinstance(provider, dict)
            else content.get("publisher")
        )
        canonical = content.get("canonicalUrl")
        url = (
            canonical.get("url") if isinstance(canonical, dict) else content.get("link")
        )
        normalized.append(
            {
                "id": str(raw.get("id") or content.get("id") or uuid4()),
                "title": title,
                "summary": str(content.get("summary") or "").strip(),
                "published_at": published_at.isoformat(),
                "publisher": publisher,
                "url": url,
            }
        )
    normalized.sort(key=lambda item: item["published_at"], reverse=True)
    return normalized[:limit]


def _trading_window_start(
    instrument: yf.Ticker, end_date: date, *, trading_days: int
) -> date:
    """Resolve the earliest date in the latest N-session Yahoo window."""

    initial_start = end_date - timedelta(days=120)
    frame = instrument.history(
        start=initial_start.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        auto_adjust=False,
    )
    if len(frame) < trading_days:
        initial_start = end_date - timedelta(days=180)
        frame = instrument.history(
            start=initial_start.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
    if frame.empty:
        return initial_start
    return frame.index[-trading_days].date() if len(frame) >= trading_days else frame.index[0].date()


def _published_at(content: dict[str, Any]) -> datetime | None:
    value = content.get("pubDate") or content.get("displayTime")
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    timestamp = content.get("providerPublishTime")
    if timestamp:
        try:
            return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    return None


def _research_inputs(
    info: dict[str, Any],
    news: list[dict[str, Any]],
    start_date: date,
    as_of_date: date,
) -> dict[str, Any]:
    profile_source = f"yfinance:AAPL:profile:{as_of_date}"
    industry = info.get("industry") or "Consumer Electronics"
    sector = info.get("sector") or "Technology"
    profile_evidence = [
        _evidence(
            profile_source,
            "company_profile",
            f"Yahoo Finance classifies Apple in {sector} / {industry}.",
            confidence=0.85,
            metadata={
                "provider": "yfinance",
                "ticker": "AAPL",
                "url": "https://finance.yahoo.com/quote/AAPL/",
            },
        )
    ]
    news_evidence = [
        _evidence(
            f"yfinance:news:{item['id']}",
            "news",
            item["title"],
            quote=item.get("summary"),
            published_at=item["published_at"],
            confidence=0.75,
            metadata={
                "provider": "yfinance",
                "publisher": item.get("publisher"),
                "url": item.get("url"),
                "window_start": start_date.isoformat(),
                "window_end": as_of_date.isoformat(),
            },
        )
        for item in news
    ]
    events = [
        {
            "event_type": "other",
            "event_summary": item["title"],
            "event_date": item["published_at"][:10],
            "published_at": item["published_at"],
            "impact_direction": "neutral",
            "certainty": "low",
            "impact_horizon": "unknown",
            "source_id": f"yfinance:news:{item['id']}",
        }
        for item in news
    ]
    return {
        "industry_report": {
            "summary": f"Apple is classified by Yahoo Finance in {sector} / {industry}.",
            "evidence": profile_evidence,
        },
        "business": {
            "business_summary": str(info.get("longBusinessSummary") or "")[:3000],
            "industry_linkage": "unknown",
            "company_type": "unknown",
            "evidence": profile_evidence,
        },
        "marginal_change": {
            "events": events,
            "direction": "neutral",
            "certainty": "low",
            "impact_horizon": "unknown",
            "evidence": news_evidence,
        },
        "company_valuation": {
            "current_market_cap": info.get("marketCap"),
            "current_market_cap_currency": info.get("currency") or "USD",
            "confidence_score": 0.8,
            "evidence": profile_evidence,
        },
        "sentiment": {
            "sentiment_score": 0,
            "heat_score": min(len(news) / 36, 1),
            "positive_items": [],
            "negative_items": [],
            "evidence": news_evidence,
        },
    }


def _evidence(
    source_id: str,
    evidence_type: str,
    claim: str,
    *,
    quote: str | None = None,
    published_at: str | None = None,
    confidence: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "evidence_id": str(uuid4()),
        "source_id": source_id,
        "evidence_type": evidence_type,
        "claim_text": claim,
        "quote_text": quote[:500] if quote else None,
        "extraction_method": "api",
        "confidence_score": confidence,
        "published_at": published_at,
        "metadata": metadata,
    }


def _database_counts(dsn: str, run_id: str) -> dict[str, int | str]:
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT status FROM analysis_runs WHERE id=%s),
                (SELECT count(*) FROM node_runs WHERE run_id=%s),
                (SELECT count(*) FROM provider_fetch_runs WHERE run_id=%s),
                (SELECT count(*) FROM evidence_items WHERE run_id=%s),
                (SELECT count(*) FROM final_reports WHERE run_id=%s),
                (SELECT count(*) FROM llm_invocations WHERE run_id=%s),
                (SELECT count(*) FROM intraday_market_bars WHERE run_id=%s)
            """,
            (run_id, run_id, run_id, run_id, run_id, run_id, run_id),
        )
        status, nodes, providers, evidence, reports, llm_calls, intraday = cursor.fetchone()
    return {
        "status": status,
        "node_runs": nodes,
        "provider_fetch_runs": providers,
        "evidence_items": evidence,
        "final_reports": reports,
        "llm_invocations": llm_calls,
        "intraday_market_bars": intraday,
    }


def _llm_summary(results: dict[str, Any]) -> dict[str, int]:
    values = list(results.values())
    return {
        "total": len(values),
        "completed": sum(1 for item in values if item.get("status") == "completed"),
        "failed": sum(1 for item in values if item.get("status") != "completed"),
        "estimated_prompt_tokens": sum(
            int(item.get("projection_manifest", {}).get("estimated_prompt_tokens", 0) or 0)
            for item in values
        ),
        "prompt_tokens": sum(
            int(item.get("usage", {}).get("prompt_tokens", 0) or 0)
            for item in values
        ),
        "completion_tokens": sum(
            int(item.get("usage", {}).get("completion_tokens", 0) or 0)
            for item in values
        ),
    }


if __name__ == "__main__":
    main()
