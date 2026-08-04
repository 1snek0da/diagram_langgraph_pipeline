"""Small helpers shared by otherwise independent agent nodes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ..dependencies import AgentDependencies
from ..schemas.research import DatasetKind, EntityRef, EvidenceItem, SourceRequest, topic_model_for


TOPIC_DATASETS = {
    "industry_report": DatasetKind.INDUSTRY_REPORTS,
    "upstream_capex": DatasetKind.CAPEX,
    "policy": DatasetKind.POLICY,
    "industry_valuation": DatasetKind.INDUSTRY_VALUATION,
    "business": DatasetKind.COMPANY_PROFILE,
    "profit_forecast": DatasetKind.PROFIT_FORECASTS,
    "marginal_change": DatasetKind.MARGINAL_EVENTS,
    "company_valuation": DatasetKind.COMPANY_VALUATION,
    "sentiment": DatasetKind.SENTIMENT,
}

DEFAULT_UPSTREAM_ENTITIES = (
    EntityRef(entity_id="alphabet", name="Alphabet", ticker="GOOGL", cik="1652044", role="demand"),
    EntityRef(entity_id="amazon", name="Amazon", ticker="AMZN", cik="1018724", role="demand"),
    EntityRef(entity_id="microsoft", name="Microsoft", ticker="MSFT", cik="789019", role="demand"),
    EntityRef(entity_id="meta", name="Meta", ticker="META", cik="1326801", role="demand"),
    EntityRef(entity_id="oracle", name="Oracle", ticker="ORCL", cik="1341439", role="demand"),
    EntityRef(entity_id="nvidia", name="NVIDIA", ticker="NVDA", cik="1045810", role="supply"),
)

KNOWN_SEC_CIKS = {
    "AAPL": "320193",
}


def topic(deps: AgentDependencies, name: str, state: dict[str, Any]) -> dict[str, Any]:
    as_of = _date_value(state.get("as_of_date")) or date.today()
    ticker = str(state.get("ticker", "")).strip()
    entities = list(DEFAULT_UPSTREAM_ENTITIES) if name in {"industry_report", "upstream_capex"} else []
    if ticker:
        target_cik = state.get("company_cik") or state.get("cik")
        if not target_cik:
            target_cik = KNOWN_SEC_CIKS.get(ticker.upper())
        entities.append(
            EntityRef(
                entity_id=ticker,
                name=str(state.get("company_name") or ticker),
                ticker=ticker,
                cik=(
                    str(target_cik)
                    if target_cik and name == "profit_forecast"
                    else None
                ),
                role="target",
            )
        )
    request_start = as_of - timedelta(days=365 * 5 + 5)
    if name in {"marginal_change", "sentiment"}:
        request_start = (
            _date_value(state.get("research_window_start"))
            or as_of
            - timedelta(days=max(30, int(state.get("market_history_days", 120))))
        )
    request = SourceRequest(
        dataset_kind=TOPIC_DATASETS[name],
        run_id=str(state.get("run_id", "pending")),
        as_of_date=as_of,
        industry_code=state.get("industry_code"),
        industry_name=state.get("industry_name"),
        entities=entities,
        start_date=request_start,
        end_date=as_of,
        history_years=5,
        forecast_years=[as_of.year + 1, as_of.year + 2],
        base_currency="CNY",
        topic=name,
        parameters={
            "legacy_payload": state.get("research_inputs", {}).get(name, {}),
            "licensed_report_paths": state.get("licensed_report_paths", []),
            "policy_urls": state.get("policy_urls", []),
            "news_limit": int(state.get("news_limit", 36) or 36),
        },
    )
    batch = deps.research.fetch(request)
    record_fetch = getattr(deps.repository, "record_provider_fetch", None)
    if callable(record_fetch):
        record_fetch(
            request.run_id,
            str(getattr(deps.research, "name", type(deps.research).__name__)),
            request.dataset_kind.value,
            request.model_dump(mode="json", exclude={"parameters": {"legacy_payload"}}),
            {
                "status": (
                    "partial"
                    if batch.errors and (batch.data or batch.documents or batch.facts)
                    else "unavailable"
                    if batch.errors
                    and all(
                        "unavailable" in error.lower()
                        or "not installed" in error.lower()
                        or "not configured" in error.lower()
                        for error in batch.errors
                    )
                    else "failed"
                    if batch.errors
                    else "completed"
                ),
                "document_count": len(batch.documents),
                "fact_count": len(batch.facts),
                "evidence_count": len(batch.evidence),
                "coverage": batch.coverage.model_dump(mode="json"),
                "warnings": batch.warnings,
                "errors": batch.errors,
            },
        )
    model = topic_model_for(name).model_validate(batch.data)
    payload = model.model_dump(mode="python")
    evidence_by_id = {
        item.get("evidence_id"): item
        for item in payload.get("evidence", [])
        if isinstance(item, dict)
    }
    for item in batch.evidence:
        dumped = item.model_dump(mode="python")
        evidence_by_id.setdefault(dumped["evidence_id"], dumped)
    for fact in batch.facts:
        if fact.evidence_ids:
            continue
        item = EvidenceItem(
            source_id=fact.source_id or f"{fact.provider}:{fact.entity_id}:{fact.metric_key}",
            evidence_type="metric_fact",
            metric_key=fact.metric_key,
            claim_text=(
                f"{fact.entity_id} {fact.metric_key} "
                f"{fact.fiscal_year or fact.period_end}: {fact.value} {fact.currency or fact.unit}"
            ),
            extraction_method=fact.basis.value,
            confidence_score=fact.confidence_score,
            published_at=fact.observed_at,
            metadata={"provider": fact.provider, "fact_id": fact.fact_id},
        )
        dumped = item.model_dump(mode="python")
        evidence_by_id.setdefault(dumped["evidence_id"], dumped)
    payload["evidence"] = list(evidence_by_id.values())
    payload["source_coverage"] = batch.coverage.model_dump(mode="python")
    payload["source_warnings"] = batch.warnings
    payload["source_errors"] = batch.errors
    payload["source_documents"] = [
        item.model_dump(mode="python", exclude={"text"})
        for item in batch.documents
    ]
    payload["metric_facts"] = [item.model_dump(mode="python") for item in batch.facts]
    return payload


def evidence_from(payload: dict[str, Any], evidence_type: str) -> list[dict[str, Any]]:
    items = payload.get("evidence", [])
    if not isinstance(items, list):
        items = [items]
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized = dict(item)
        else:
            normalized = {"claim_text": str(item)}
        normalized.setdefault("evidence_type", evidence_type)
        normalized.setdefault("confidence_score", 0.5)
        result.append(normalized)
    return result


def number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def mean_or_none(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return sum(valid) / len(valid) if valid else None


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
