"""Yahoo-backed company profile, valuation, news, and sentiment adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from typing import Any
from uuid import uuid4

from ..schemas.research import (
    CoverageReport,
    DatasetKind,
    EvidenceItem,
    SourceBatch,
    SourceDocument,
    SourceRequest,
    SourceTier,
)


class YahooResearchAdapter:
    name = "yahoo_research"
    capabilities = frozenset(
        {
            DatasetKind.COMPANY_PROFILE,
            DatasetKind.COMPANY_VALUATION,
            DatasetKind.MARGINAL_EVENTS,
            DatasetKind.SENTIMENT,
        }
    )

    def __init__(self, cache_dir: str | None = None) -> None:
        self.cache_dir = cache_dir or os.getenv("YFINANCE_CACHE_DIR")

    def fetch(self, request: SourceRequest) -> SourceBatch:
        target = next(
            (entity for entity in request.entities if entity.role == "target"), None
        )
        if target is None or not target.ticker:
            return SourceBatch(errors=["Yahoo research requires a target ticker"])
        instrument = self._instrument(target.ticker)
        try:
            info = instrument.info or {}
        except Exception as exc:
            return SourceBatch(errors=[f"Yahoo profile failed: {type(exc).__name__}: {exc}"])
        if request.dataset_kind == DatasetKind.COMPANY_PROFILE:
            return _profile_batch(target, info)
        if request.dataset_kind == DatasetKind.COMPANY_VALUATION:
            return _valuation_batch(target, info)
        news = _news_items(
            instrument,
            request.start_date,
            request.end_date,
            int(request.parameters.get("news_limit", 36) or 36),
        )
        if request.dataset_kind == DatasetKind.MARGINAL_EVENTS:
            return _marginal_batch(target, news)
        return _sentiment_batch(target, news)

    def resolve_security(self, ticker: str) -> dict[str, Any]:
        info = self._instrument(ticker).info or {}
        if not info:
            raise RuntimeError(f"Yahoo returned no metadata for {ticker}")
        return {
            "ticker": ticker.upper(),
            "company_name": info.get("longName") or info.get("shortName") or ticker.upper(),
            "market": _market_name(ticker, info),
            "exchange": info.get("exchange") or info.get("fullExchangeName") or "UNKNOWN",
            "industry_name": info.get("industry") or info.get("sector") or "Unknown",
            "sector": info.get("sector"),
            "currency": info.get("currency"),
            "external_ids": {},
        }

    def _instrument(self, ticker: str):
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("Install yfinance to use YahooResearchAdapter") from exc
        if self.cache_dir:
            yf.set_tz_cache_location(self.cache_dir)
        return yf.Ticker(ticker)


def _profile_batch(target, info: dict[str, Any]) -> SourceBatch:
    source_id = f"yahoo:{target.ticker}:profile"
    raw = json.dumps(info, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    document = SourceDocument(
        source_id=source_id,
        provider="yahoo_research",
        source_tier=SourceTier.SECONDARY_NEWS,
        source_type="company_profile",
        external_id=target.ticker,
        title=f"{target.name} Yahoo company profile",
        publisher="Yahoo Finance",
        url=f"https://finance.yahoo.com/quote/{target.ticker}/profile/",
        content_hash=sha256(raw).hexdigest(),
        language="en-US",
        license_scope="provider_terms",
        metadata={"ticker": target.ticker, "sector": info.get("sector"), "industry": info.get("industry")},
    )
    evidence = EvidenceItem(
        source_id=source_id,
        evidence_type="company_profile",
        claim_text=f"Yahoo classifies {target.name} in {info.get('sector')} / {info.get('industry')}",
        extraction_method="api",
        confidence_score=Decimal("0.8"),
        metadata={"provider": "yahoo_research", "url": document.url},
    )
    data = {
        "business_summary": str(info.get("longBusinessSummary") or "")[:6000],
        "revenue_segments": [],
        "industry_linkage": "unknown",
        "growth_drivers": [],
        "risks": [],
        "company_type": "unknown",
    }
    return SourceBatch(
        data=data,
        documents=[document],
        evidence=[evidence],
        coverage=CoverageReport.from_items(["business_summary"], ["business_summary"] if data["business_summary"] else []),
    )


def _valuation_batch(target, info: dict[str, Any]) -> SourceBatch:
    market_cap = info.get("marketCap")
    return SourceBatch(
        data={
            "current_market_cap": market_cap,
            "current_market_cap_currency": info.get("currency") or "USD",
            "confidence_score": Decimal("0.8") if market_cap else Decimal("0.2"),
        },
        coverage=CoverageReport.from_items(
            ["current_market_cap"], ["current_market_cap"] if market_cap else []
        ),
    )


def _marginal_batch(target, news: list[dict[str, Any]]) -> SourceBatch:
    documents, evidence = _news_evidence(target, news)
    events = [
        {
            "event_type": "other",
            "event_summary": item["title"],
            "event_date": item["published_at"][:10],
            "published_at": item["published_at"],
            "impact_direction": "neutral",
            "certainty": "low",
            "impact_horizon": "unknown",
            "source_id": item["source_id"],
        }
        for item in news
    ]
    return SourceBatch(
        data={
            "events": events,
            "direction": "neutral",
            "certainty": "low",
            "impact_horizon": "unknown",
        },
        documents=documents,
        evidence=evidence,
        coverage=CoverageReport.from_items(["events"], ["events"] if events else []),
        warnings=[] if events else ["Yahoo returned no news in the requested window"],
    )


def _sentiment_batch(target, news: list[dict[str, Any]]) -> SourceBatch:
    documents, evidence = _news_evidence(target, news)
    positive_words = ("beat", "record", "surge", "growth", "upgrade", "gain")
    negative_words = ("miss", "fall", "drop", "risk", "warning", "cut")
    positive = [item for item in news if any(word in item["title"].lower() for word in positive_words)]
    negative = [item for item in news if any(word in item["title"].lower() for word in negative_words)]
    denominator = max(1, len(news))
    score = Decimal(len(positive) - len(negative)) / Decimal(denominator)
    return SourceBatch(
        data={
            "sentiment_score": max(Decimal("-1"), min(Decimal("1"), score)),
            "heat_score": min(Decimal("1"), Decimal(len(news)) / Decimal("36")),
            "positive_items": [item["title"] for item in positive],
            "negative_items": [item["title"] for item in negative],
        },
        documents=documents,
        evidence=evidence,
        coverage=CoverageReport.from_items(["sentiment_score", "heat_score"], ["sentiment_score", "heat_score"]),
        warnings=[] if news else ["Yahoo returned no news in the requested window"],
    )


def _news_items(instrument, start_date, end_date, limit: int) -> list[dict[str, Any]]:
    try:
        raw_items = instrument.get_news(count=max(100, limit * 3), tab="news") or []
    except (AttributeError, TypeError):
        raw_items = instrument.news or []
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc) if start_date else datetime.min.replace(tzinfo=timezone.utc)
    end = datetime.combine((end_date or datetime.now(timezone.utc).date()) + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
        title = str(content.get("title") or "").strip()
        published = _published_at(content)
        if not title or published is None or not start <= published < end:
            continue
        canonical = content.get("canonicalUrl")
        url = canonical.get("url") if isinstance(canonical, dict) else content.get("link")
        identity = str(raw.get("id") or content.get("id") or url or title)
        if identity in seen:
            continue
        seen.add(identity)
        provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher")
        result.append(
            {
                "source_id": f"yahoo:news:{identity}",
                "title": title,
                "summary": str(content.get("summary") or "")[:1200],
                "published_at": published.isoformat(),
                "publisher": publisher,
                "url": url,
            }
        )
    result.sort(key=lambda item: item["published_at"], reverse=True)
    return result[:limit]


def _news_evidence(target, news):
    documents: list[SourceDocument] = []
    evidence: list[EvidenceItem] = []
    for item in news:
        content_hash = sha256(
            json.dumps(item, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        documents.append(
            SourceDocument(
                source_id=item["source_id"],
                provider="yahoo_research",
                source_tier=SourceTier.SECONDARY_NEWS,
                source_type="news",
                external_id=item["source_id"].rsplit(":", 1)[-1],
                title=item["title"],
                publisher=item.get("publisher"),
                published_at=datetime.fromisoformat(item["published_at"]),
                url=item.get("url"),
                content_hash=content_hash,
                language="en-US",
                license_scope="provider_terms",
                metadata={"ticker": target.ticker},
            )
        )
        evidence.append(
            EvidenceItem(
                evidence_id=str(uuid4()),
                source_id=item["source_id"],
                evidence_type="news",
                claim_text=item["title"],
                quote_text=item.get("summary"),
                extraction_method="api",
                confidence_score=Decimal("0.7"),
                published_at=datetime.fromisoformat(item["published_at"]),
                metadata={"provider": "yahoo_research", "url": item.get("url")},
            )
        )
    return documents, evidence


def _published_at(content: dict[str, Any]) -> datetime | None:
    value = content.get("pubDate") or content.get("displayTime")
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    timestamp = content.get("providerPublishTime")
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc) if timestamp else None
    except (TypeError, ValueError, OSError):
        return None


def _market_name(ticker: str, info: dict[str, Any]) -> str:
    upper = ticker.upper()
    if upper.endswith((".SS", ".SZ")):
        return "CN"
    if upper.endswith(".HK"):
        return "HK"
    return str(info.get("market") or "US").upper()
