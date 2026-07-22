"""Deterministic market-data provider for tests and offline runs."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any


class InMemoryMarketDataProvider:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self._payloads = payloads

    def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        payload = deepcopy(self._payloads.get(ticker, {}))
        payload.setdefault("bars", [])
        payload.setdefault("valuations", [])
        payload.setdefault("source", "in_memory")
        payload["requested_range"] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        return payload
