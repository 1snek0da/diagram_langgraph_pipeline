"""As-of-safe marginal change and near-term catalyst node."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "marginal_change", state)
    as_of = _date_value(state.get("as_of_date")) or date.today()
    events = []
    excluded = []
    for item in payload.get("events", []):
        published = _date_value(item.get("published_at"))
        if published is None:
            excluded.append({"reason": "missing_published_at", "event": item})
            continue
        if published > as_of:
            excluded.append({"reason": "after_as_of_date", "event": item})
            continue
        events.append(item)
    positive = sum(item.get("impact_direction") == "positive" for item in events)
    negative = sum(item.get("impact_direction") == "negative" for item in events)
    direction = "positive" if positive > negative else "negative" if negative > positive else "neutral"
    certainties = [item.get("certainty", "medium") for item in events]
    certainty = "low" if not certainties else "high" if all(value == "high" for value in certainties) else "medium"
    return {
        "marginal_change_result": {
            "direction": payload.get("direction") or direction,
            "events": events,
            "excluded_events": excluded,
            "certainty": payload.get("certainty") or certainty,
            "impact_horizon": payload.get("impact_horizon") or "unknown",
            "missing_items": [] if events else ["缺少带发布日期且不晚于as_of_date的边际变化事件"],
            "source_coverage": payload.get("source_coverage", {}),
            "source_warnings": payload.get("source_warnings", []),
            "source_errors": payload.get("source_errors", []),
            "evidence": evidence_from(payload, "marginal_change"),
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
