"""SEC EDGAR XBRL adapter for reported overseas capital expenditure."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Any

from bs4 import BeautifulSoup
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


CAPEX_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
)

QUARTERLY_DURATION_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ),
    "net_profit": ("NetIncomeLoss", "ProfitLoss"),
    "gross_profit": ("GrossProfit",),
    "research_expense": ("ResearchAndDevelopmentExpense",),
}

QUARTERLY_INSTANT_TAGS: dict[str, tuple[str, ...]] = {
    "inventory": ("InventoryNet",),
    "contract_liabilities": (
        "ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueCurrent",
    ),
}


class SecEdgarAdapter:
    name = "sec_edgar"
    capabilities = frozenset({DatasetKind.CAPEX, DatasetKind.PROFIT_FORECASTS})

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ):
        if "@" not in user_agent:
            raise ValueError("SEC user_agent must include a contact email")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self._client = client or ResilientHttpTransport(HttpPolicy(timeout_seconds=timeout_seconds))

    def fetch(self, request: SourceRequest) -> SourceBatch:
        if request.dataset_kind == DatasetKind.PROFIT_FORECASTS:
            return self._fetch_quarterly_financials(request)
        return self._fetch_capex(request)

    def _fetch_capex(self, request: SourceRequest) -> SourceBatch:
        requested = [entity.entity_id for entity in request.entities if entity.cik]
        available: list[str] = []
        documents: list[SourceDocument] = []
        facts: list[MetricFact] = []
        errors: list[str] = []
        warnings = ["SEC XBRL仅提供企业总CapEx；通信相关CapEx必须由披露或授权研报补充"]

        for entity in request.entities:
            if not entity.cik:
                continue
            try:
                payload = self._get_company_facts(entity.cik)
                entity_facts, entity_docs = _extract_annual_capex(payload, entity, request)
                if not entity_facts:
                    fallback_facts, fallback_docs = self._extract_from_raw_filings(entity, request)
                    entity_facts.extend(fallback_facts)
                    entity_docs.extend(fallback_docs)
                    if fallback_facts:
                        warnings.append(f"{entity.name}: Company Facts标签缺失，已从原始10-K启发式提取并标记extracted")
                facts.extend(entity_facts)
                documents.extend(entity_docs)
                if entity_facts:
                    available.append(entity.entity_id)
            except Exception as exc:
                errors.append(f"{entity.name}: {type(exc).__name__}: {exc}")

        return SourceBatch(
            facts=facts,
            documents=documents,
            coverage=CoverageReport.from_items(requested, available, errors=errors),
            warnings=warnings,
            errors=errors,
        )

    def _fetch_quarterly_financials(self, request: SourceRequest) -> SourceBatch:
        targets = [entity for entity in request.entities if entity.role == "target"]
        requested = [entity.entity_id for entity in targets]
        available: list[str] = []
        rows: list[dict[str, Any]] = []
        documents: list[SourceDocument] = []
        facts: list[MetricFact] = []
        errors: list[str] = []
        warnings: list[str] = []

        for entity in targets:
            if not entity.cik:
                resolved = self._resolve_cik(entity.ticker)
                if resolved is None:
                    errors.append(
                        f"{entity.name}: SEC is not applicable or no CIK was found"
                    )
                    continue
                entity = entity.model_copy(update={"cik": resolved})
            try:
                payload = self._get_company_facts(entity.cik)
                entity_rows, entity_facts, entity_documents = (
                    _extract_quarterly_financials(payload, entity, request)
                )
                rows.extend(entity_rows)
                facts.extend(entity_facts)
                documents.extend(entity_documents)
                if entity_rows:
                    available.append(entity.entity_id)
                if len(entity_rows) < 8:
                    warnings.append(
                        f"{entity.name}: SEC returned {len(entity_rows)} usable quarters; expected 8"
                    )
            except Exception as exc:
                errors.append(f"{entity.name}: {type(exc).__name__}: {exc}")

        rows.sort(key=lambda item: str(item.get("period_end", "")))
        return SourceBatch(
            data={"quarterly_financials": rows},
            facts=facts,
            documents=documents,
            coverage=CoverageReport.from_items(requested, available, errors=errors),
            warnings=warnings,
            errors=errors,
        )

    def _resolve_cik(self, ticker: str | None) -> str | None:
        if not ticker or "." in ticker:
            return None
        url = "https://www.sec.gov/files/company_tickers.json"
        response = self._client.get(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
        )
        response.raise_for_status()
        target = ticker.upper()
        for item in response.json().values():
            if str(item.get("ticker", "")).upper() == target:
                return str(item.get("cik_str", "")).zfill(10)
        return None

    def resolve_cik(self, ticker: str) -> str | None:
        """Resolve one US ticker for metadata caching by the DB-first service."""
        return self._resolve_cik(ticker)

    def _get_company_facts(self, cik: str) -> dict:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        response = self._client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def _extract_from_raw_filings(self, entity, request: SourceRequest) -> tuple[list[MetricFact], list[SourceDocument]]:
        submissions_url = f"https://data.sec.gov/submissions/CIK{entity.cik}.json"
        response = self._client.get(
            submissions_url,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
        )
        response.raise_for_status()
        recent = response.json().get("filings", {}).get("recent", {})
        rows = _submission_rows(recent)
        cutoff = request.as_of_date
        minimum_year = request.as_of_date.year - request.history_years
        selected: dict[int, dict] = {}
        for item in rows:
            if item.get("form") != "10-K":
                continue
            filed = _parse_date(item.get("filingDate"))
            report_date = _parse_date(item.get("reportDate"))
            if filed is None or report_date is None or filed > cutoff or report_date.year < minimum_year:
                continue
            selected.setdefault(report_date.year, item)

        facts: list[MetricFact] = []
        documents: list[SourceDocument] = []
        for fiscal_year, item in sorted(selected.items()):
            accession = str(item.get("accessionNumber") or "")
            primary_document = str(item.get("primaryDocument") or "")
            if not accession or not primary_document:
                continue
            url = _primary_document_url(entity.cik, accession, primary_document)
            filing_response = self._client.get(url, headers={"User-Agent": self.user_agent})
            filing_response.raise_for_status()
            extracted = _extract_capex_from_filing_html(filing_response.text, fiscal_year)
            if extracted is None:
                continue
            value, scale, label = extracted
            source_id = f"sec:{entity.cik}:{accession}:raw-capex"
            filed_at = _parse_datetime(item.get("filingDate"))
            documents.append(
                SourceDocument(
                    source_id=source_id,
                    provider=self.name,
                    source_tier=SourceTier.PRIMARY_OFFICIAL,
                    source_type="sec_10k_raw_extraction",
                    external_id=accession,
                    title=f"{entity.name} {fiscal_year} 10-K raw CapEx extraction",
                    publisher="U.S. Securities and Exchange Commission",
                    published_at=filed_at,
                    url=url,
                    content_hash=sha256(filing_response.content).hexdigest(),
                    language="en-US",
                    license_scope="public",
                    metadata={"matched_label": label, "extraction_method": "cash_flow_row_heuristic"},
                )
            )
            facts.append(
                MetricFact(
                    metric_key="total_capex",
                    entity_id=entity.entity_id,
                    period_end=_parse_date(item.get("reportDate")),
                    fiscal_year=fiscal_year,
                    value=value,
                    currency="USD",
                    unit="currency",
                    scale=scale,
                    basis=FactBasis.EXTRACTED,
                    provider=self.name,
                    source_id=source_id,
                    observed_at=filed_at,
                    confidence_score=Decimal("0.55"),
                    metadata={
                        "entity_name": entity.name,
                        "role": entity.role,
                        "accession": accession,
                        "matched_label": label,
                    },
                )
            )
        return facts, documents


def _extract_quarterly_financials(
    payload: dict[str, Any], entity, request: SourceRequest
) -> tuple[list[dict[str, Any]], list[MetricFact], list[SourceDocument]]:
    concepts = payload.get("facts", {}).get("us-gaap", {})
    cutoff = datetime.combine(request.as_of_date, time.max, tzinfo=timezone.utc)
    series: dict[str, dict[tuple[int, int], dict[str, Any]]] = {}
    for metric, tags in QUARTERLY_DURATION_TAGS.items():
        series[metric] = _duration_quarter_series(concepts, tags, cutoff)
    for metric, tags in QUARTERLY_INSTANT_TAGS.items():
        series[metric] = _instant_quarter_series(concepts, tags, cutoff)

    keys = set(series.get("revenue", {})) | set(series.get("net_profit", {}))
    ordered_keys = sorted(
        keys,
        key=lambda key: (
            _point_end(series, key) or date.min,
            key,
        ),
    )[-8:]

    rows: list[dict[str, Any]] = []
    facts: list[MetricFact] = []
    documents: dict[str, SourceDocument] = {}
    for fiscal_year, quarter in ordered_keys:
        metric_points = {
            metric: values.get((fiscal_year, quarter))
            for metric, values in series.items()
        }
        representative = next(
            (point for point in metric_points.values() if point is not None), None
        )
        if representative is None:
            continue
        period_end = representative["period_end"]
        revenue = _point_value(metric_points.get("revenue"))
        net_profit = _point_value(metric_points.get("net_profit"))
        gross_profit = _point_value(metric_points.get("gross_profit"))
        source_ids: list[str] = []
        filed_values: list[datetime] = []
        row: dict[str, Any] = {
            "entity_id": entity.entity_id,
            "company_name": entity.name,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "period": f"FY{fiscal_year}Q{quarter}",
            "period_end": period_end,
            "currency": "USD",
            "unit": "currency",
            "scale": Decimal("1"),
            "revenue": revenue,
            "net_profit": net_profit,
            "adjusted_net_profit": None,
            "gross_profit": gross_profit,
            "gross_margin": (
                gross_profit / revenue
                if gross_profit is not None and revenue not in {None, Decimal("0")}
                else None
            ),
            "net_margin": (
                net_profit / revenue
                if net_profit is not None and revenue not in {None, Decimal("0")}
                else None
            ),
            "research_expense": _point_value(
                metric_points.get("research_expense")
            ),
            "inventory": _point_value(metric_points.get("inventory")),
            "contract_liabilities": _point_value(
                metric_points.get("contract_liabilities")
            ),
            "provider": "sec_edgar",
        }

        for metric, point in metric_points.items():
            if point is None or point.get("value") is None:
                continue
            source_id = _quarter_source_id(entity.cik, point["accession"])
            source_ids.append(source_id)
            if point.get("filed_at"):
                filed_values.append(point["filed_at"])
            documents.setdefault(
                source_id,
                _quarter_source_document(entity, fiscal_year, quarter, point),
            )
            facts.append(
                MetricFact(
                    metric_key=f"quarterly_{metric}",
                    entity_id=entity.entity_id,
                    period_end=period_end,
                    fiscal_year=fiscal_year,
                    value=point["value"],
                    currency="USD",
                    unit="currency",
                    basis=(
                        FactBasis.DERIVED
                        if point.get("derived")
                        else FactBasis.REPORTED
                    ),
                    provider="sec_edgar",
                    source_id=source_id,
                    observed_at=point.get("filed_at"),
                    metadata={
                        "entity_name": entity.name,
                        "role": entity.role,
                        "fiscal_quarter": quarter,
                        "xbrl_tag": point.get("tag"),
                        "accession": point.get("accession"),
                        "derived_from": point.get("derived_from", []),
                    },
                )
            )
        row["source_ids"] = list(dict.fromkeys(source_ids))
        row["filed_at"] = max(filed_values) if filed_values else None
        row["fact_basis"] = (
            "derived"
            if any(point and point.get("derived") for point in metric_points.values())
            else "reported"
        )
        rows.append(row)

    return rows, facts, list(documents.values())


def _duration_quarter_series(
    concepts: dict[str, Any], tags: tuple[str, ...], cutoff: datetime
) -> dict[tuple[int, int], dict[str, Any]]:
    tag, units = _concept_units(concepts, tags)
    if tag is None:
        return {}
    quarterly: dict[tuple[int, int], list[dict[str, Any]]] = {}
    annual: dict[int, list[dict[str, Any]]] = {}
    for item in units:
        normalized = _normalized_sec_item(item, cutoff, require_start=True)
        if normalized is None:
            continue
        fiscal_year = normalized["fiscal_year"]
        fiscal_period = normalized["fiscal_period"]
        duration_days = normalized["duration_days"]
        normalized["tag"] = tag
        if fiscal_period in {"Q1", "Q2", "Q3"} and 45 <= duration_days <= 150:
            quarter = int(fiscal_period[1])
            quarterly.setdefault((fiscal_year, quarter), []).append(normalized)
        elif fiscal_period == "FY" and 250 <= duration_days <= 450:
            annual.setdefault(fiscal_year, []).append(normalized)

    result = {
        key: _select_current_period(items)
        for key, items in quarterly.items()
    }
    for fiscal_year, items in annual.items():
        annual_point = _select_current_period(items)
        components = [result.get((fiscal_year, quarter)) for quarter in (1, 2, 3)]
        if all(point is not None for point in components):
            component_values = [point["value"] for point in components if point]
            annual_point = dict(annual_point)
            annual_point["value"] = annual_point["value"] - sum(
                component_values, Decimal("0")
            )
            annual_point["derived"] = True
            annual_point["derived_from"] = [
                point["accession"] for point in components if point
            ] + [annual_point["accession"]]
            result[(fiscal_year, 4)] = annual_point
    return result


def _instant_quarter_series(
    concepts: dict[str, Any], tags: tuple[str, ...], cutoff: datetime
) -> dict[tuple[int, int], dict[str, Any]]:
    tag, units = _concept_units(concepts, tags)
    if tag is None:
        return {}
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for item in units:
        normalized = _normalized_sec_item(item, cutoff, require_start=False)
        if normalized is None:
            continue
        fiscal_period = normalized["fiscal_period"]
        if fiscal_period in {"Q1", "Q2", "Q3"}:
            quarter = int(fiscal_period[1])
        elif fiscal_period == "FY":
            quarter = 4
        else:
            continue
        normalized["tag"] = tag
        grouped.setdefault((normalized["fiscal_year"], quarter), []).append(
            normalized
        )
    return {key: _select_current_period(items) for key, items in grouped.items()}


def _concept_units(
    concepts: dict[str, Any], tags: tuple[str, ...]
) -> tuple[str | None, list[dict[str, Any]]]:
    for tag in tags:
        units = concepts.get(tag, {}).get("units", {}).get("USD", [])
        if units:
            return tag, units
    return None, []


def _normalized_sec_item(
    item: dict[str, Any], cutoff: datetime, *, require_start: bool
) -> dict[str, Any] | None:
    if item.get("form") not in {"10-Q", "10-K"} or item.get("val") is None:
        return None
    filed_at = _parse_datetime(item.get("filed"))
    period_end = _parse_date(item.get("end"))
    fiscal_year = item.get("fy")
    if (
        filed_at is None
        or filed_at > cutoff
        or period_end is None
        or not isinstance(fiscal_year, int)
    ):
        return None
    period_start = _parse_date(item.get("start"))
    if require_start and period_start is None:
        return None
    return {
        "value": Decimal(str(item["val"])),
        "period_start": period_start,
        "period_end": period_end,
        "duration_days": (
            (period_end - period_start).days + 1 if period_start else 0
        ),
        "fiscal_year": fiscal_year,
        "fiscal_period": str(item.get("fp") or ""),
        "filed_at": filed_at,
        "accession": str(item.get("accn") or ""),
        "form": str(item.get("form")),
        "derived": False,
    }


def _select_current_period(items: list[dict[str, Any]]) -> dict[str, Any]:
    latest_end = max(item["period_end"] for item in items)
    same_period = [item for item in items if item["period_end"] == latest_end]
    return max(same_period, key=lambda item: item["filed_at"])


def _point_end(
    series: dict[str, dict[tuple[int, int], dict[str, Any]]],
    key: tuple[int, int],
) -> date | None:
    for values in series.values():
        point = values.get(key)
        if point is not None:
            return point["period_end"]
    return None


def _point_value(point: dict[str, Any] | None) -> Decimal | None:
    return point.get("value") if point else None


def _quarter_source_id(cik: str, accession: str) -> str:
    return f"sec:{cik}:{accession}:quarterly-financials"


def _quarter_source_document(
    entity, fiscal_year: int, quarter: int, point: dict[str, Any]
) -> SourceDocument:
    accession = point["accession"]
    source_id = _quarter_source_id(entity.cik, accession)
    return SourceDocument(
        source_id=source_id,
        provider="sec_edgar",
        source_tier=SourceTier.PRIMARY_OFFICIAL,
        source_type=(
            "sec_10k_xbrl" if point.get("form") == "10-K" else "sec_10q_xbrl"
        ),
        external_id=accession or None,
        title=f"{entity.name} FY{fiscal_year} Q{quarter} SEC XBRL facts",
        publisher="U.S. Securities and Exchange Commission",
        published_at=point.get("filed_at"),
        url=_filing_url(entity.cik, accession),
        content_hash=sha256(source_id.encode("utf-8")).hexdigest(),
        language="en-US",
        license_scope="public",
        metadata={"xbrl_tag": point.get("tag"), "derived": point.get("derived", False)},
    )


def _extract_annual_capex(payload: dict, entity, request: SourceRequest) -> tuple[list[MetricFact], list[SourceDocument]]:
    concepts = payload.get("facts", {}).get("us-gaap", {})
    selected_tag = next((tag for tag in CAPEX_TAGS if tag in concepts), None)
    if selected_tag is None:
        return [], []
    units = concepts[selected_tag].get("units", {}).get("USD", [])
    cutoff = datetime.combine(request.as_of_date, time.max, tzinfo=timezone.utc)
    by_year: dict[int, dict] = {}
    for item in units:
        if item.get("form") != "10-K" or item.get("fp") != "FY" or item.get("val") is None:
            continue
        filed = _parse_datetime(item.get("filed"))
        if filed is None or filed > cutoff:
            continue
        fiscal_year = item.get("fy")
        if not isinstance(fiscal_year, int):
            continue
        current = by_year.get(fiscal_year)
        if current is None or str(item.get("filed")) > str(current.get("filed")):
            by_year[fiscal_year] = item

    minimum_year = request.as_of_date.year - request.history_years
    facts: list[MetricFact] = []
    documents: list[SourceDocument] = []
    for fiscal_year, item in sorted(by_year.items()):
        if fiscal_year < minimum_year:
            continue
        accession = str(item.get("accn", ""))
        source_id = f"sec:{entity.cik}:{accession}:{selected_tag}"
        raw = json.dumps(item, sort_keys=True, ensure_ascii=True).encode()
        filed = _parse_datetime(item.get("filed"))
        document = SourceDocument(
            source_id=source_id,
            provider="sec_edgar",
            source_tier=SourceTier.PRIMARY_OFFICIAL,
            source_type="sec_10k_xbrl",
            external_id=accession or None,
            title=f"{entity.name} {fiscal_year} 10-K {selected_tag}",
            publisher="U.S. Securities and Exchange Commission",
            published_at=filed,
            url=_filing_url(entity.cik, accession),
            content_hash=sha256(raw).hexdigest(),
            language="en-US",
            license_scope="public",
            metadata={"xbrl_tag": selected_tag, "frame": item.get("frame")},
        )
        documents.append(document)
        facts.append(
            MetricFact(
                metric_key="total_capex",
                entity_id=entity.entity_id,
                period_end=_parse_date(item.get("end")),
                fiscal_year=fiscal_year,
                value=Decimal(str(item["val"])),
                currency="USD",
                unit="currency",
                basis=FactBasis.REPORTED,
                provider="sec_edgar",
                source_id=source_id,
                observed_at=filed,
                metadata={
                    "entity_name": entity.name,
                    "role": entity.role,
                    "xbrl_tag": selected_tag,
                    "accession": accession,
                },
            )
        )
    return facts, documents


def _filing_url(cik: str, accession: str) -> str | None:
    if not accession:
        return None
    accession_compact = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_compact}/"


def _primary_document_url(cik: str, accession: str, primary_document: str) -> str:
    return f"{_filing_url(cik, accession)}{primary_document}"


def _submission_rows(recent: dict) -> list[dict]:
    keys = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument")
    lengths = [len(recent.get(key, [])) for key in keys]
    count = min(lengths) if lengths else 0
    return [{key: recent[key][index] for key in keys} for index in range(count)]


CAPEX_LABELS = (
    "purchases of property and equipment",
    "payments to acquire property plant and equipment",
    "capital expenditures",
    "additions to property and equipment",
)


def _extract_capex_from_filing_html(html: str, fiscal_year: int) -> tuple[Decimal, Decimal, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    scale = _filing_scale(soup.get_text(" ", strip=True))
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if not cells:
            continue
        label = cells[0].lower()
        if not any(pattern in label for pattern in CAPEX_LABELS):
            continue
        values = cells[1:]
        if values and re.fullmatch(r"20\d{2}", values[0].replace(" ", "")):
            if int(values[0].replace(" ", "")) != fiscal_year:
                continue
            values = values[1:]
        amount = next((_money_value(value) for value in values if _money_value(value) is not None), None)
        if amount is not None:
            return abs(amount), scale, cells[0]
    return None


def _filing_scale(text: str) -> Decimal:
    normalized = text.lower()
    if "in millions" in normalized or "millions of dollars" in normalized:
        return Decimal("1000000")
    if "in thousands" in normalized or "thousands of dollars" in normalized:
        return Decimal("1000")
    return Decimal("1")


def _money_value(value: str) -> Decimal | None:
    normalized = value.strip().replace("$", "").replace(",", "").replace("−", "-")
    negative = normalized.startswith("(") and normalized.endswith(")")
    normalized = normalized.strip("() ")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", normalized):
        return None
    amount = Decimal(normalized)
    return -amount if negative else amount


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value[:10]).date()
