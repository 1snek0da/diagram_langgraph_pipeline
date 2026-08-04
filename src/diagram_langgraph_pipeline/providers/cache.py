"""Database-first provider wrappers shared by the CLI and graph."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any

from ..contracts import (
    DataCacheRepository,
    MarketDataProvider,
    ProviderPolicy,
    ResearchResponseCache,
    ResearchSourceAdapter,
    RunEvent,
    RunEventSink,
)
from ..events import NullEventSink
from ..schemas.research import CoverageReport, SourceBatch, SourceRequest
from .composite_research import _merge_batches


SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|passwd|secret|database_url|dsn|token)$",
    re.IGNORECASE,
)


class DatabaseFirstMarketDataProvider:
    """Read normalized PostgreSQL bars first and fill only stale/incomplete ranges."""

    def __init__(
        self,
        upstream: MarketDataProvider,
        cache: DataCacheRepository,
        *,
        report_days: int,
        technical_days: int,
        intraday_interval: str = "60m",
        offline: bool = False,
        refresh: bool = False,
        events: RunEventSink | None = None,
    ) -> None:
        self.upstream = upstream
        self.cache = cache
        self.report_days = report_days
        self.technical_days = technical_days
        self.required_days = max(report_days, technical_days)
        self.intraday_interval = intraday_interval
        self.offline = offline
        self.refresh = refresh
        self.events = events or NullEventSink()
        self._refreshed_tickers: set[str] = set()

    def fetch(self, ticker: str, start_date: date, end_date: date) -> dict[str, Any]:
        ticker = ticker.upper()
        force_refresh = self.refresh and ticker not in self._refreshed_tickers
        lookup_start = min(
            start_date,
            end_date - timedelta(days=min(3650, 2 * self.required_days + 30)),
        )
        self._event(ticker, "started", "查询PostgreSQL行情缓存")
        cached = self.cache.load_market_data(
            ticker,
            lookup_start,
            end_date,
            intraday_interval=self.intraday_interval,
        )
        cached_bars = _merge_rows([], cached.get("bars", []), "trade_date")
        complete = (
            len(cached_bars) >= self.required_days
            and _is_fresh(cached_bars, end_date)
            and bool(cached.get("minute_bars"))
            and bool(cached.get("valuations"))
        )
        if complete and not force_refresh:
            result = _market_result(
                cached,
                bars=cached_bars[-self.required_days :],
                source="postgres_cache",
                cache_status="cache_hit",
                db_count=len(cached_bars),
                api_count=0,
                interval=self.intraday_interval,
            )
            self._event(ticker, "completed", "数据库缓存命中", result["metadata"])
            return result

        if self.offline:
            status = "cache_partial" if cached_bars else "offline_miss"
            result = _market_result(
                cached,
                bars=cached_bars[-self.required_days :],
                source="postgres_cache",
                cache_status=status,
                db_count=len(cached_bars),
                api_count=0,
                interval=self.intraday_interval,
            )
            self._event(ticker, "degraded", "离线模式无法补齐行情", result["metadata"])
            return result

        fetch_start = end_date - timedelta(
            days=min(3650, 2 * self.required_days + 30)
        )
        status = "refresh" if force_refresh else "cache_partial" if cached_bars else "cache_miss"
        self._event(
            ticker,
            "started",
            "调用Yahoo补齐行情",
            {"cache_status": status, "start_date": fetch_start.isoformat()},
        )
        try:
            live = self.upstream.fetch(ticker, fetch_start, end_date)
        except Exception as exc:
            if force_refresh:
                self._refreshed_tickers.add(ticker)
            result = _market_result(
                cached,
                bars=cached_bars[-self.required_days :],
                source="postgres_cache",
                cache_status=status,
                db_count=len(cached_bars),
                api_count=0,
                interval=self.intraday_interval,
            )
            result["metadata"]["provider_error"] = type(exc).__name__
            self._event(
                ticker,
                "degraded" if cached_bars else "failed",
                f"Yahoo 行情补采失败：{type(exc).__name__}",
                result["metadata"],
            )
            return result
        live_bars = list(live.get("bars", []))
        if force_refresh:
            self._refreshed_tickers.add(ticker)
        merged_bars = _merge_rows(cached_bars, live_bars, "trade_date")
        merged_intraday = _merge_rows(
            cached.get("minute_bars", []), live.get("minute_bars", []), "trade_date"
        )
        merged_valuations = _merge_rows(
            cached.get("valuations", []), live.get("valuations", []), "trade_date"
        )
        persisted = {
            **live,
            "bars": merged_bars,
            "minute_bars": merged_intraday,
            "valuations": merged_valuations,
            "source": str(live.get("source", "yfinance")),
        }
        self.cache.save_market_cache(ticker, persisted)
        result = _market_result(
            persisted,
            bars=merged_bars[-self.required_days :],
            source=str(live.get("source", "yfinance")),
            cache_status=status,
            db_count=len(cached_bars),
            api_count=len(live_bars),
            interval=self.intraday_interval,
        )
        self._event(ticker, "completed", "行情补采完成", result["metadata"])
        return result

    def fetch_daily(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        return list(self.fetch(ticker, start_date, end_date).get("bars", []))

    def _event(
        self,
        ticker: str,
        status: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events.emit(
            RunEvent(
                event_type="provider",
                stage=f"market:{ticker}",
                status=status,  # type: ignore[arg-type]
                message=message,
                metadata=metadata or {},
            )
        )


class CachedResearchSourceAdapter:
    """Cache one network adapter without caching caller-supplied research inputs."""

    def __init__(
        self,
        adapter: ResearchSourceAdapter,
        cache: ResearchResponseCache,
        *,
        policy: ProviderPolicy | None = None,
        offline: bool = False,
        refresh: bool = False,
        allowed: bool = True,
        events: RunEventSink | None = None,
    ) -> None:
        self.adapter = adapter
        self.cache = cache
        self.policy = policy or ProviderPolicy()
        self.offline = offline
        self.refresh = refresh
        self.allowed = allowed
        self.events = events or NullEventSink()
        self.name = adapter.name
        self.capabilities = adapter.capabilities

    def fetch(self, request: SourceRequest) -> SourceBatch:
        scope_hash, safe_request = research_scope(request, self.name)
        cached_row = self.cache.load_research_cache(
            self.name,
            request.dataset_kind.value,
            scope_hash,
            request.as_of_date,
            request.start_date,
            request.end_date,
            allow_expired=self.offline,
        )
        cached = (
            SourceBatch.model_validate(cached_row["response"])
            if cached_row and cached_row.get("response")
            else None
        )
        future_removed = False
        if cached is not None:
            cached, future_removed = _remove_future_evidence(
                cached, request.as_of_date
            )
        if (
            cached is not None
            and not self.refresh
            and _batch_complete(cached)
            and _cache_covers(cached_row, request)
            and not future_removed
        ):
            self._event(request, "completed", "研究缓存命中", "cache_hit")
            return cached
        if self.offline or not self.allowed:
            if cached is not None:
                self._event(request, "degraded", "仅使用部分研究缓存", "cache_partial")
                return cached
            reason = "offline_miss" if self.offline else "provider_not_authorized"
            self._event(request, "degraded", "研究数据不可补采", reason)
            return SourceBatch(
                coverage=CoverageReport(),
                errors=[f"{self.name}: {reason}"],
            )

        cache_status = "refresh" if self.refresh else "cache_partial" if cached else "cache_miss"
        self._event(request, "started", "调用研究Provider", cache_status)
        try:
            live = self.adapter.fetch(request)
        except Exception as exc:
            live = SourceBatch(errors=[f"{self.name}: {type(exc).__name__}: {exc}"])
        merged = _merge_batches([batch for batch in (cached, live) if batch], request)
        status = (
            "completed"
            if _batch_complete(merged)
            else "partial"
            if merged.data or merged.documents or merged.facts or merged.evidence
            else "failed"
        )
        ttl = _request_ttl(request, self.policy) if status == "completed" else 900
        if self.policy.cache_mode == "full":
            self.cache.save_research_cache(
                {
                    "provider": self.name,
                    "dataset_kind": request.dataset_kind.value,
                    "scope_hash": scope_hash,
                    "request": safe_request,
                    "response": merged.model_dump(mode="json"),
                    "cache_as_of_date": request.as_of_date,
                    "coverage_start": request.start_date,
                    "coverage_end": request.end_date,
                    "status": status,
                    "coverage_ratio": merged.coverage.coverage_ratio,
                    "schema_version": 1,
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl),
                }
            )
        self._event(
            request,
            "completed" if status == "completed" else "degraded",
            "研究Provider处理完成",
            cache_status,
        )
        return merged

    def _event(
        self, request: SourceRequest, status: str, message: str, cache_status: str
    ) -> None:
        self.events.emit(
            RunEvent(
                event_type="provider",
                stage=f"research:{self.name}:{request.dataset_kind.value}",
                status=status,  # type: ignore[arg-type]
                message=message,
                metadata={"cache_status": cache_status},
            )
        )


def research_scope(request: SourceRequest, provider: str) -> tuple[str, dict[str, Any]]:
    payload = request.model_dump(mode="json")
    payload.pop("run_id", None)
    parameters = payload.get("parameters", {})
    if isinstance(parameters, dict):
        parameters.pop("legacy_payload", None)
    safe = _remove_sensitive(payload)
    scope = deepcopy(safe)
    for key in ("as_of_date", "start_date", "end_date"):
        scope.pop(key, None)
    scope["provider"] = provider
    canonical = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest(), safe


def _remove_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_sensitive(item)
            for key, item in value.items()
            if not SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, list):
        return [_remove_sensitive(item) for item in value]
    return value


def _batch_complete(batch: SourceBatch) -> bool:
    return not batch.errors and not batch.coverage.missing_items


def _cache_covers(row: dict[str, Any] | None, request: SourceRequest) -> bool:
    if not row:
        return False
    start = row.get("coverage_start")
    end = row.get("coverage_end")
    return (
        (request.start_date is None or start is None or start <= request.start_date)
        and (request.end_date is None or end is None or end >= request.end_date)
    )


def _request_ttl(request: SourceRequest, policy: ProviderPolicy) -> int:
    kind = request.dataset_kind.value
    if kind == "company_profile":
        return 7 * 86_400
    if kind in {"sentiment", "marginal_events"}:
        return 1_800
    return policy.ttl_seconds


def _remove_future_evidence(
    batch: SourceBatch, as_of_date: date
) -> tuple[SourceBatch, bool]:
    documents = [
        item
        for item in batch.documents
        if item.published_at is None or item.published_at.date() <= as_of_date
    ]
    evidence = [
        item
        for item in batch.evidence
        if (item.published_at is None or item.published_at.date() <= as_of_date)
    ]
    removed_ids = {
        item.source_id for item in batch.documents if item not in documents
    }
    evidence = [item for item in evidence if item.source_id not in removed_ids]
    facts = [item for item in batch.facts if item.source_id not in removed_ids]
    changed = (
        len(documents) != len(batch.documents)
        or len(evidence) != len(batch.evidence)
        or len(facts) != len(batch.facts)
    )
    if not changed:
        return batch, False
    return batch.model_copy(
        update={
            "documents": documents,
            "evidence": evidence,
            "facts": facts,
            "warnings": [*batch.warnings, "future evidence removed for as-of safety"],
        }
    ), True


def _merge_rows(
    left: list[dict[str, Any]], right: list[dict[str, Any]], key: str
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in [*left, *right]:
        value = str(item.get(key, ""))
        if value:
            merged[value] = dict(item)
    return [merged[value] for value in sorted(merged)]


def _is_fresh(bars: list[dict[str, Any]], end_date: date) -> bool:
    if not bars:
        return False
    try:
        latest = date.fromisoformat(str(bars[-1]["trade_date"])[:10])
    except (KeyError, ValueError):
        return False
    return 0 <= (end_date - latest).days <= 7


def _market_result(
    payload: dict[str, Any],
    *,
    bars: list[dict[str, Any]],
    source: str,
    cache_status: str,
    db_count: int,
    api_count: int,
    interval: str,
) -> dict[str, Any]:
    metadata = dict(payload.get("metadata", {}))
    metadata.update(
        {
            "cache_status": cache_status,
            "database_bar_count": db_count,
            "api_bar_count": api_count,
            "intraday_interval": interval,
            "persistence_managed": True,
        }
    )
    return {
        **payload,
        "bars": bars,
        "source": source,
        "metadata": metadata,
    }
