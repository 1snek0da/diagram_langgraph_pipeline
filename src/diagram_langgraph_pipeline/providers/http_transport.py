"""Shared bounded-retry, rate-limited and in-memory cached HTTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
from typing import Any

import httpx


@dataclass(frozen=True)
class HttpPolicy:
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    minimum_interval_seconds: float = 0.1
    cache_enabled: bool = True


class ResilientHttpTransport:
    """Small synchronous transport shared by network-backed adapters.

    Cache lifetime is intentionally limited to the current process. Long-lived
    persistence belongs in provider fetch-run storage where provenance is kept.
    """

    def __init__(self, policy: HttpPolicy | None = None, client: httpx.Client | None = None):
        self.policy = policy or HttpPolicy()
        self._client = client or httpx.Client(timeout=self.policy.timeout_seconds)
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], httpx.Response] = {}
        self._lock = Lock()
        self._last_request_at = 0.0

    def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        key = (url, tuple(sorted((str(name), str(value)) for name, value in (params or {}).items())))
        if self.policy.cache_enabled and key in self._cache:
            return self._cache[key]

        last_error: Exception | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            self._throttle()
            try:
                response = self._client.get(url, params=params, headers=headers)
                response.raise_for_status()
                if self.policy.cache_enabled:
                    self._cache[key] = response
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise
                if attempt < self.policy.max_attempts:
                    sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))
        assert last_error is not None
        raise last_error

    def _throttle(self) -> None:
        with self._lock:
            elapsed = monotonic() - self._last_request_at
            remaining = self.policy.minimum_interval_seconds - elapsed
            if remaining > 0:
                sleep(remaining)
            self._last_request_at = monotonic()
