"""Research provider backed by caller-supplied state payloads."""

from __future__ import annotations

from typing import Any


class InputResearchProvider:
    def get_topic(self, topic: str, state: dict[str, Any]) -> dict[str, Any]:
        value = state.get("research_inputs", {}).get(topic, {})
        return dict(value) if isinstance(value, dict) else {"items": value}
