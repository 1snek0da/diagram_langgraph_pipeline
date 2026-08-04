from datetime import date, datetime, timedelta, timezone

from diagram_langgraph_pipeline.contracts import ProviderPolicy
from diagram_langgraph_pipeline.providers.cache import (
    CachedResearchSourceAdapter,
    DatabaseFirstMarketDataProvider,
    research_scope,
)
from diagram_langgraph_pipeline.schemas import (
    CoverageReport,
    DatasetKind,
    EntityRef,
    SourceBatch,
    SourceRequest,
)


def _bars(count=8):
    start = date(2026, 7, 1)
    return [
        {
            "trade_date": (start + timedelta(days=index)).isoformat(),
            "open": 10 + index,
            "high": 11 + index,
            "low": 9 + index,
            "close": 10.5 + index,
            "volume": 100,
        }
        for index in range(count)
    ]


class MarketCache:
    def __init__(self, payload):
        self.payload = payload
        self.saved = []

    def load_market_data(self, *args, **kwargs):
        return self.payload

    def save_market_cache(self, ticker, payload):
        self.saved.append((ticker, payload))


class MarketUpstream:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def fetch(self, *args):
        self.calls += 1
        return self.payload


def test_market_complete_cache_avoids_yahoo():
    cached = {
        "bars": _bars(),
        "minute_bars": [{"trade_date": "2026-07-08T10:00:00+00:00", "close": 17}],
        "valuations": [{"trade_date": "2026-07-08", "pe_ttm": 20}],
        "source": "postgres_cache",
    }
    upstream = MarketUpstream({})
    provider = DatabaseFirstMarketDataProvider(
        upstream, MarketCache(cached), report_days=5, technical_days=5
    )

    result = provider.fetch("AAPL", date(2026, 6, 1), date(2026, 7, 8))

    assert upstream.calls == 0
    assert result["metadata"]["cache_status"] == "cache_hit"
    assert len(result["bars"]) == 5


def test_market_partial_cache_fetches_and_persists():
    cache = MarketCache({"bars": _bars(2), "minute_bars": [], "valuations": []})
    upstream = MarketUpstream(
        {
            "bars": _bars(),
            "minute_bars": [{"trade_date": "2026-07-08T10:00:00+00:00", "close": 17}],
            "valuations": [{"trade_date": "2026-07-08", "pe_ttm": 20}],
            "source": "yfinance",
        }
    )
    provider = DatabaseFirstMarketDataProvider(
        upstream, cache, report_days=5, technical_days=5
    )

    result = provider.fetch("AAPL", date(2026, 6, 1), date(2026, 7, 8))

    assert upstream.calls == 1
    assert cache.saved
    assert result["metadata"]["cache_status"] == "cache_partial"


def test_market_offline_never_calls_upstream():
    upstream = MarketUpstream({"bars": _bars()})
    provider = DatabaseFirstMarketDataProvider(
        upstream,
        MarketCache({"bars": _bars(2), "minute_bars": [], "valuations": []}),
        report_days=5,
        technical_days=5,
        offline=True,
    )

    result = provider.fetch("AAPL", date(2026, 6, 1), date(2026, 7, 8))

    assert upstream.calls == 0
    assert result["metadata"]["cache_status"] == "cache_partial"


def test_market_refresh_forces_upstream_even_when_complete():
    cached = {
        "bars": _bars(),
        "minute_bars": [{"trade_date": "2026-07-08T10:00:00+00:00", "close": 17}],
        "valuations": [{"trade_date": "2026-07-08", "pe_ttm": 20}],
    }
    upstream = MarketUpstream({**cached, "source": "yfinance"})
    provider = DatabaseFirstMarketDataProvider(
        upstream, MarketCache(cached), report_days=5, technical_days=5, refresh=True
    )

    result = provider.fetch("AAPL", date(2026, 6, 1), date(2026, 7, 8))

    assert upstream.calls == 1
    assert result["metadata"]["cache_status"] == "refresh"


def _request(parameters=None):
    return SourceRequest(
        dataset_kind=DatasetKind.SENTIMENT,
        run_id="secret-run-id",
        as_of_date=date(2026, 7, 8),
        start_date=date(2026, 6, 1),
        entities=[EntityRef(entity_id="aapl", name="Apple", ticker="AAPL", role="target")],
        parameters=parameters or {},
    )


def test_research_scope_is_stable_and_removes_secrets_and_legacy_payload():
    first_hash, safe = research_scope(
        _request({"api_key": "secret", "legacy_payload": {"huge": True}, "news_limit": 36}),
        "yahoo_research",
    )
    second = _request({"api_key": "different", "legacy_payload": {"x": 1}, "news_limit": 36})
    second.run_id = "another-run"
    second_hash, _ = research_scope(second, "yahoo_research")

    assert first_hash == second_hash
    assert "api_key" not in safe["parameters"]
    assert "legacy_payload" not in safe["parameters"]
    assert "run_id" not in safe


class ResearchCache:
    def __init__(self, row=None):
        self.row = row
        self.saved = []

    def load_research_cache(self, *args, **kwargs):
        return self.row

    def save_research_cache(self, payload):
        self.saved.append(payload)


class ResearchUpstream:
    name = "fake_research"
    capabilities = frozenset({DatasetKind.SENTIMENT})

    def __init__(self):
        self.calls = 0

    def fetch(self, request):
        self.calls += 1
        return SourceBatch(
            data={"records": [{"title": "news"}]},
            coverage=CoverageReport(
                requested_items=["news"], available_items=["news"], coverage_ratio=1
            ),
        )


def test_research_full_cache_avoids_provider_and_offline_miss_does_not_call():
    batch = SourceBatch(
        data={"records": [{"title": "cached"}]},
        coverage=CoverageReport(
            requested_items=["news"], available_items=["news"], coverage_ratio=1
        ),
    )
    row = {
        "response": batch.model_dump(mode="json"),
        "coverage_start": date(2026, 6, 1),
        "coverage_end": date(2026, 7, 8),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    upstream = ResearchUpstream()
    result = CachedResearchSourceAdapter(upstream, ResearchCache(row)).fetch(_request())
    assert upstream.calls == 0
    assert result.data["records"][0]["title"] == "cached"

    offline_upstream = ResearchUpstream()
    missing = CachedResearchSourceAdapter(
        offline_upstream, ResearchCache(), offline=True, policy=ProviderPolicy()
    ).fetch(_request())
    assert offline_upstream.calls == 0
    assert missing.errors
