"""Allowlisted official-policy page fetcher; it does not discover or crawl sites."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx

from ..schemas.research import CoverageReport, DatasetKind, SourceBatch, SourceDocument, SourceRequest, SourceTier
from .http_transport import HttpPolicy, ResilientHttpTransport


DEFAULT_ALLOWED_HOST_SUFFIXES = (
    "gov.cn",
    "miit.gov.cn",
    "ndrc.gov.cn",
    "csrc.gov.cn",
)


class OfficialPolicyWebAdapter:
    name = "official_policy_web"
    capabilities = frozenset({DatasetKind.POLICY})

    def __init__(
        self,
        *,
        allowed_host_suffixes: tuple[str, ...] = DEFAULT_ALLOWED_HOST_SUFFIXES,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ):
        self.allowed_host_suffixes = allowed_host_suffixes
        self.timeout_seconds = timeout_seconds
        self._client = client or ResilientHttpTransport(HttpPolicy(timeout_seconds=timeout_seconds))

    def fetch(self, request: SourceRequest) -> SourceBatch:
        urls = [str(value) for value in request.parameters.get("policy_urls", [])]
        documents: list[SourceDocument] = []
        errors: list[str] = []
        for url in urls:
            try:
                host = (urlparse(url).hostname or "").lower()
                if not any(host == suffix or host.endswith(f".{suffix}") for suffix in self.allowed_host_suffixes):
                    raise ValueError(f"host not allowlisted: {host}")
                response = self._client.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                title = soup.title.get_text(strip=True) if soup.title else url
                text = soup.get_text("\n", strip=True)
                published_at = _find_published_at(soup)
                if published_at and published_at.date() > request.as_of_date:
                    continue
                documents.append(
                    SourceDocument(
                        provider=self.name,
                        source_tier=SourceTier.PRIMARY_OFFICIAL,
                        source_type="official_policy",
                        title=title,
                        publisher=host,
                        published_at=published_at,
                        url=url,
                        content_hash=sha256(response.content).hexdigest(),
                        language="zh-CN",
                        license_scope="public",
                        text=text,
                    )
                )
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
        return SourceBatch(
            documents=documents,
            coverage=CoverageReport.from_items(urls, [item.url or item.title for item in documents], errors=errors),
            errors=errors,
        )


def _find_published_at(soup: BeautifulSoup) -> datetime | None:
    for name in ("article:published_time", "pubdate", "publishdate", "date"):
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        value = tag.get("content") if tag else None
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
