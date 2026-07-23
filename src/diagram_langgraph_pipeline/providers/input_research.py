"""Validated research provider backed by caller-supplied state payloads."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..schemas.research import (
    CoverageReport,
    DatasetKind,
    EvidenceItem,
    SourceBatch,
    SourceRequest,
    topic_model_for,
)


REQUIRED_TOPIC_FIELDS: dict[str, list[str]] = {
    "industry_report": ["summary"],
    "upstream_capex": ["records"],
    "policy": ["summary"],
    "industry_valuation": ["current_market_cap"],
    "business": ["business_summary"],
    "profit_forecast": ["forecasts"],
    "marginal_change": ["events"],
    "company_valuation": ["current_market_cap"],
    "sentiment": ["sentiment_score", "heat_score"],
}


class InputResearchProvider:
    """Compatibility adapter that validates ``state.research_inputs``."""

    name = "input"
    capabilities = frozenset(DatasetKind)

    def fetch(self, request: SourceRequest) -> SourceBatch:
        topic = request.topic
        if not topic:
            return SourceBatch(
                coverage=CoverageReport(),
                errors=["InputResearchProvider requires request.topic"],
            )
        value = request.parameters.get("legacy_payload", {})
        raw = dict(value) if isinstance(value, dict) else {"items": value}
        raw = _normalize_legacy(topic, raw)
        try:
            model = topic_model_for(topic).model_validate(raw)
        except ValidationError as exc:
            return SourceBatch(
                coverage=CoverageReport.from_items(REQUIRED_TOPIC_FIELDS.get(topic, []), []),
                errors=[f"invalid input for {topic}: {exc}"],
            )

        data = model.model_dump(mode="python")
        evidence = [EvidenceItem.model_validate(item) for item in data.pop("evidence", [])]
        data["evidence"] = [item.model_dump(mode="python") for item in evidence]
        requested = REQUIRED_TOPIC_FIELDS.get(topic, [])
        available = [field for field in requested if _has_value(data.get(field))]
        warnings: list[str] = []
        if topic == "profit_forecast":
            undated = [item for item in data.get("forecasts", []) if item.get("published_at") is None]
            if undated:
                warnings.append("存在无 published_at 的兼容预测记录；生产数据应提供发布日期")
        return SourceBatch(
            data=data,
            evidence=evidence,
            coverage=CoverageReport.from_items(requested, available),
            warnings=warnings,
        )


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _normalize_legacy(topic: str, raw: dict[str, Any]) -> dict[str, Any]:
    result = dict(raw)
    evidence = result.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [evidence]
    result["evidence"] = [
        item if isinstance(item, dict) else {"claim_text": str(item)}
        for item in evidence
    ]
    if topic == "marginal_change":
        aliases = {
            "capacity_release": "capacity",
            "product_certification": "certification",
            "new_order": "order",
        }
        normalized_events = []
        for item in result.get("events", []):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            normalized["event_type"] = aliases.get(normalized.get("event_type"), normalized.get("event_type", "other"))
            normalized_events.append(normalized)
        result["events"] = normalized_events
    return result
