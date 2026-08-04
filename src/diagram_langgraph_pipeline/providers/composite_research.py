"""Composable routing and merge layer for research-source adapters."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from ..contracts import ResearchSourceAdapter
from ..schemas.research import CoverageReport, FactBasis, MetricFact, SourceBatch, SourceRequest


class CompositeResearchDataProvider:
    """Route a request to every capable adapter and merge partial results."""

    name = "composite"

    def __init__(self, adapters: Iterable[ResearchSourceAdapter]):
        self.adapters = tuple(adapters)

    def fetch(self, request: SourceRequest) -> SourceBatch:
        capable = [adapter for adapter in self.adapters if request.dataset_kind in adapter.capabilities]
        if not capable:
            return SourceBatch(
                coverage=CoverageReport(),
                errors=[f"no adapter supports {request.dataset_kind.value}"],
            )

        batches: list[SourceBatch] = []
        for adapter in capable:
            try:
                batches.append(adapter.fetch(request))
            except Exception as exc:  # Provider failures must remain local to the batch.
                batches.append(SourceBatch(errors=[f"{adapter.name}: {type(exc).__name__}: {exc}"]))
        return _merge_batches(batches, request)


def _merge_batches(batches: list[SourceBatch], request: SourceRequest) -> SourceBatch:
    data: dict = {}
    documents = {}
    facts = {}
    evidence = {}
    warnings: list[str] = []
    errors: list[str] = []
    requested: list[str] = []
    available: list[str] = []
    latest = None

    for batch in batches:
        data = _deep_merge(data, batch.data)
        for document in batch.documents:
            documents.setdefault(document.content_hash, document)
            if document.published_at and (latest is None or document.published_at > latest):
                latest = document.published_at
        for fact in batch.facts:
            key = (
                fact.entity_id,
                fact.metric_key,
                fact.period_start,
                fact.period_end,
                fact.fiscal_year,
                fact.source_id or fact.provider,
            )
            facts.setdefault(key, fact)
        for item in batch.evidence:
            evidence.setdefault(item.evidence_id, item)
        requested.extend(batch.coverage.requested_items)
        available.extend(batch.coverage.available_items)
        warnings.extend(batch.warnings)
        errors.extend(batch.errors)
        errors.extend(batch.coverage.source_errors)

    merged_data = _inject_fact_data(data, list(facts.values())) if request.dataset_kind.value == "capex" else data
    if merged_data.get("records") and "records" in requested:
        available.append("records")
    coverage = CoverageReport.from_items(requested, available, errors=errors)
    coverage.latest_published_at = latest
    if not requested:
        coverage.coverage_ratio = Decimal("0") if errors else Decimal("1")
    return SourceBatch(
        data=merged_data,
        documents=list(documents.values()),
        facts=list(facts.values()),
        evidence=list(evidence.values()),
        coverage=coverage,
        warnings=list(dict.fromkeys(warnings)),
        errors=list(dict.fromkeys(errors)),
    )


def _deep_merge(left: dict, right: dict) -> dict:
    merged = dict(left)
    for key, value in right.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        elif isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = [*merged[key], *value]
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _inject_fact_data(data: dict, facts: list[MetricFact]) -> dict:
    """Expose normalized capex facts to legacy-compatible node payloads."""

    if not any(fact.metric_key in {"total_capex", "communication_capex"} for fact in facts):
        return data
    result = dict(data)
    record_index: dict[tuple[str, int | None, str | None], dict] = {}
    for item in result.get("records", []):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id") or item.get("company_name", "")).lower().replace(" ", "_")
        key = (entity_id, item.get("fiscal_year"), item.get("currency"))
        record_index[key] = dict(item)

    basis_priority = {
        FactBasis.DERIVED.value: 0,
        FactBasis.ESTIMATED.value: 1,
        FactBasis.EXTRACTED.value: 2,
        FactBasis.REPORTED.value: 3,
    }
    for fact in facts:
        if fact.metric_key not in {"total_capex", "communication_capex"}:
            continue
        key = (fact.entity_id, fact.fiscal_year, fact.currency)
        record = record_index.setdefault(
            key,
            {
                "entity_id": fact.entity_id,
                "company_name": fact.metadata.get("entity_name", fact.entity_id),
                "role": fact.metadata.get("role", "other"),
                "fiscal_year": fact.fiscal_year,
                "currency": fact.currency,
                "unit": fact.unit,
                "scale": fact.scale,
            },
        )
        basis_field = f"{fact.metric_key}_basis"
        existing_raw = record.get(basis_field, record.get("fact_basis", "estimated"))
        existing_basis = existing_raw.value if isinstance(existing_raw, FactBasis) else str(existing_raw)
        incoming_basis = fact.basis.value
        if record.get(fact.metric_key) is None or basis_priority[incoming_basis] >= basis_priority.get(existing_basis, 0):
            record[fact.metric_key] = fact.value
            record["fact_basis"] = incoming_basis
            record[basis_field] = incoming_basis
            record[f"{fact.metric_key}_source_id"] = fact.source_id
    result["records"] = list(record_index.values())
    return result
