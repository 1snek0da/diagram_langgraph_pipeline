"""Configurable adapter for the official CNINFO Data Service."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

import httpx

from ..schemas.research import CoverageReport, DatasetKind, SourceBatch, SourceDocument, SourceRequest, SourceTier
from .http_transport import HttpPolicy, ResilientHttpTransport


class CninfoAdapter:
    """Use licensed CNINFO endpoints supplied by configuration.

    CNINFO products use account-specific endpoint and authentication settings,
    so this adapter deliberately does not guess an undocumented public route.
    """

    name = "cninfo"
    capabilities = frozenset({DatasetKind.ANNOUNCEMENTS, DatasetKind.MARGINAL_EVENTS, DatasetKind.COMPANY_PROFILE})

    def __init__(
        self,
        *,
        base_url: str,
        dataset_paths: dict[DatasetKind, str],
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.dataset_paths = dataset_paths
        self.headers = dict(headers or {})
        self.timeout_seconds = timeout_seconds
        self._client = client or ResilientHttpTransport(HttpPolicy(timeout_seconds=timeout_seconds))

    def fetch(self, request: SourceRequest) -> SourceBatch:
        path = self.dataset_paths.get(request.dataset_kind)
        if not path:
            return SourceBatch(errors=[f"CNINFO path not configured for {request.dataset_kind.value}"])
        params = {
            "scode": next((entity.ticker for entity in request.entities if entity.ticker), None),
            "sdate": (request.start_date or request.as_of_date).isoformat(),
            "edate": request.as_of_date.isoformat(),
        }
        response = self._client.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=params,
            headers=self.headers,
        )
        response.raise_for_status()
        payload = response.json()
        records = _records(payload)
        documents: list[SourceDocument] = []
        for index, record in enumerate(records):
            published_at = _published_at(record)
            if published_at and published_at.date() > request.as_of_date:
                continue
            raw = json.dumps(record, ensure_ascii=False, sort_keys=True).encode()
            documents.append(
                SourceDocument(
                    provider=self.name,
                    source_tier=SourceTier.PRIMARY_OFFICIAL,
                    source_type="company_announcement",
                    external_id=str(record.get("announcementId") or record.get("id") or index),
                    title=str(record.get("announcementTitle") or record.get("title") or "CNINFO公告"),
                    publisher="巨潮资讯",
                    published_at=published_at,
                    url=record.get("adjunctUrl") or record.get("url"),
                    content_hash=sha256(raw).hexdigest(),
                    language="zh-CN",
                    license_scope="licensed_api",
                    metadata=record,
                )
            )
        requested = [entity.entity_id for entity in request.entities] or [request.dataset_kind.value]
        available = requested if documents else []
        return SourceBatch(
            documents=documents,
            coverage=CoverageReport.from_items(requested, available),
        )


def _records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "announcements"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("records")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
    return []


def _published_at(record: dict) -> datetime | None:
    value = record.get("announcementTime") or record.get("announcementDate") or record.get("pubdate")
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
