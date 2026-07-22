"""Market sentiment and crowding node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, number, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "sentiment", state)
    score = number(payload.get("sentiment_score"), 0.0) or 0.0
    heat = number(payload.get("heat_score"), 0.0) or 0.0
    crowding = payload.get("crowding_risk")
    if crowding is None:
        crowding = "high" if heat >= 0.8 else "medium" if heat >= 0.5 else "low"
    return {
        "sentiment_result": {
            "sentiment_score": max(-1.0, min(1.0, score)),
            "heat_score": max(0.0, min(1.0, heat)),
            "crowding_risk": crowding,
            "positive_items": payload.get("positive_items", []),
            "negative_items": payload.get("negative_items", []),
            "evidence": evidence_from(payload, "sentiment"),
        }
    }
