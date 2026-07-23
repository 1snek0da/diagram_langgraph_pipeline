"""ECB reference-rate adapter for reproducible USD/CNY conversion."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timezone
from decimal import Decimal
from hashlib import sha256
from io import StringIO

import httpx

from ..schemas.research import (
    CoverageReport,
    DatasetKind,
    FactBasis,
    MetricFact,
    SourceBatch,
    SourceDocument,
    SourceRequest,
    SourceTier,
)
from .http_transport import HttpPolicy, ResilientHttpTransport


class EcbFxAdapter:
    name = "ecb_fx"
    capabilities = frozenset({DatasetKind.FX, DatasetKind.INDUSTRY_VALUATION})

    def __init__(self, *, timeout_seconds: float = 20.0, client: httpx.Client | None = None):
        self.timeout_seconds = timeout_seconds
        self._client = client or ResilientHttpTransport(HttpPolicy(timeout_seconds=timeout_seconds))

    def fetch(self, request: SourceRequest) -> SourceBatch:
        currencies = request.parameters.get("currencies", ["USD", "CNY"])
        requested = [currency.upper() for currency in currencies]
        series: dict[str, dict[date, Decimal]] = {}
        errors: list[str] = []
        documents: list[SourceDocument] = []
        for currency in requested:
            try:
                text = self._get_series(currency, request)
                values = _parse_ecb_csv(text, request.as_of_date)
                series[currency] = values
                documents.append(
                    SourceDocument(
                        provider=self.name,
                        source_tier=SourceTier.PRIMARY_OFFICIAL,
                        source_type="ecb_reference_rate",
                        external_id=f"EXR.D.{currency}.EUR.SP00.A",
                        title=f"ECB {currency}/EUR daily reference rate",
                        publisher="European Central Bank",
                        published_at=datetime.combine(request.as_of_date, time.min, tzinfo=timezone.utc),
                        url=_series_url(currency, request),
                        content_hash=sha256(text.encode()).hexdigest(),
                        language="en",
                        license_scope="public",
                    )
                )
            except Exception as exc:
                errors.append(f"{currency}: {type(exc).__name__}: {exc}")

        common_dates = set(series.get("USD", {})) & set(series.get("CNY", {}))
        common_dates = {item for item in common_dates if item <= request.as_of_date}
        facts: list[MetricFact] = []
        data: dict = {}
        available: list[str] = []
        if common_dates:
            rate_date = max(common_dates)
            cny_per_usd = series["CNY"][rate_date] / series["USD"][rate_date]
            facts.append(
                MetricFact(
                    metric_key="fx_usd_cny",
                    entity_id="USD/CNY",
                    period_end=rate_date,
                    value=cny_per_usd,
                    currency="CNY",
                    unit="CNY_per_USD",
                    basis=FactBasis.DERIVED,
                    provider=self.name,
                    metadata={"rate_date": rate_date.isoformat(), "cross_currency": "EUR"},
                )
            )
            if request.dataset_kind == DatasetKind.FX:
                data["fx_rates"] = {
                    "USD/CNY": {
                        "rate": cny_per_usd,
                        "rate_date": rate_date,
                        "basis": FactBasis.DERIVED,
                        "provider": self.name,
                    }
                }
            data["fx_rate_usd_cny"] = cny_per_usd
            data["fx_rate_date"] = rate_date
            available = requested
        return SourceBatch(
            data=data,
            facts=facts,
            documents=documents,
            coverage=CoverageReport.from_items(requested, available, errors=errors),
            errors=errors,
        )

    def _get_series(self, currency: str, request: SourceRequest) -> str:
        url = _series_url(currency, request)
        response = self._client.get(url)
        response.raise_for_status()
        return response.text


def _series_url(currency: str, request: SourceRequest) -> str:
    start = request.start_date or request.as_of_date
    return (
        f"https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
        f"?startPeriod={start.isoformat()}&endPeriod={request.as_of_date.isoformat()}&format=csvdata"
    )


def _parse_ecb_csv(text: str, cutoff: date) -> dict[date, Decimal]:
    rows = csv.DictReader(StringIO(text))
    values: dict[date, Decimal] = {}
    for row in rows:
        period = row.get("TIME_PERIOD")
        value = row.get("OBS_VALUE")
        if not period or value in (None, ""):
            continue
        item_date = date.fromisoformat(period[:10])
        if item_date <= cutoff:
            values[item_date] = Decimal(value)
    return values
