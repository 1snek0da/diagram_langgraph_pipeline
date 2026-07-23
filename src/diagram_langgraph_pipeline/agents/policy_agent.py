"""Policy impact analysis node."""

from __future__ import annotations

from typing import Any
from datetime import date, datetime

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "policy", state)
    as_of = _date_value(state.get("as_of_date")) or date.today()
    events = [
        item
        for item in payload.get("events", [])
        if not item.get("published_at") or _date_value(item.get("published_at")) <= as_of
    ]
    direction = {
        "supportive": "positive",
        "restrictive": "negative",
    }.get(payload.get("direction"), payload.get("direction", "neutral"))
    evidence = evidence_from(payload, "policy")
    quantified = payload.get("quantified_impact_pct")
    quantified_source = next(
        (
            item
            for item in events
            if item.get("quantified_impact_pct") is not None and item.get("source_id")
        ),
        None,
    )
    if quantified is None and quantified_source:
        quantified = quantified_source.get("quantified_impact_pct")
    warnings = list(payload.get("source_warnings", []))
    if quantified is not None and not evidence and quantified_source is None:
        warnings.append("量化政策影响缺少来源证据，已从数值公式中排除")
        quantified = None
    return {
        "policy_result": {
            "direction": direction,
            "magnitude": payload.get("magnitude", "unknown"),
            "impact_horizon": payload.get("impact_horizon", "unknown"),
            "affected_metrics": payload.get("affected_metrics", []),
            "quantified_impact_pct": quantified,
            "summary": payload.get("summary", "未提供可核验政策资料"),
            "events": events,
            "source_documents": payload.get("source_documents", []),
            "source_coverage": payload.get("source_coverage", {}),
            "source_warnings": warnings,
            "source_errors": payload.get("source_errors", []),
            "evidence": evidence,
        }
    }


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
