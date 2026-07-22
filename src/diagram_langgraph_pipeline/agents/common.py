"""Small helpers shared by otherwise independent agent nodes."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


def topic(deps: AgentDependencies, name: str, state: dict[str, Any]) -> dict[str, Any]:
    return deps.research.get_topic(name, state)


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
