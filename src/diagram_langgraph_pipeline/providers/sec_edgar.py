"""SEC EDGAR XBRL adapter for reported overseas capital expenditure."""

from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal
from hashlib import sha256
import json
import re

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


class SecEdgarAdapter:
    name = "sec_edgar"
    capabilities = frozenset({DatasetKind.CAPEX})

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
