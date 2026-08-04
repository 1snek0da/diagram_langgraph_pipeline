"""Environment-driven registration of optional research adapters."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from ..contracts import ProviderPolicy, ResearchResponseCache, RunEventSink
from ..schemas.research import DatasetKind
from .cninfo import CninfoAdapter
from .composite_research import CompositeResearchDataProvider
from .ecb_fx import EcbFxAdapter
from .input_research import InputResearchProvider
from .http_transport import HttpPolicy, ResilientHttpTransport
from .licensed_reports import LicensedReportDirectoryAdapter
from .policy_web import OfficialPolicyWebAdapter
from .sec_edgar import SecEdgarAdapter
from .tushare_research import TushareResearchAdapter
from .vendor_plugins import IFindResearchAdapter, WindResearchAdapter
from .yahoo_research import YahooResearchAdapter
from .cache import CachedResearchSourceAdapter


def build_research_provider(
    settings: Mapping[str, str] | None = None,
    *,
    cache: ResearchResponseCache | None = None,
    events: RunEventSink | None = None,
    offline: bool = False,
    refresh: bool = False,
    allow_paid: bool = False,
    network_enabled: bool | None = None,
) -> CompositeResearchDataProvider:
    """Build a provider that stays fully offline unless explicitly enabled."""

    values = settings or os.environ
    report_roots = [
        item
        for item in values.get("LICENSED_REPORT_DIRS", "").split(os.pathsep)
        if item
    ]
    adapters: list[Any] = [
        InputResearchProvider(),
        LicensedReportDirectoryAdapter(report_roots),
    ]
    enabled = (
        _enabled("ENABLE_NETWORK_RESEARCH", values)
        if network_enabled is None
        else network_enabled
    )
    network_adapters: list[tuple[Any, ProviderPolicy]] = []
    if enabled:
        policy = HttpPolicy(
            timeout_seconds=_float_env(
                "PROVIDER_TIMEOUT_SECONDS", 20.0, values
            ),
            max_attempts=_int_env("PROVIDER_MAX_ATTEMPTS", 3, values),
            minimum_interval_seconds=_float_env(
                "PROVIDER_MIN_INTERVAL_SECONDS", 0.1, values
            ),
        )
        user_agent = values.get("SEC_USER_AGENT", "")
        if "@" in user_agent:
            network_adapters.append(
                (
                    SecEdgarAdapter(
                        user_agent=user_agent,
                        client=ResilientHttpTransport(policy),
                    ),
                    ProviderPolicy(cost_tier="free", ttl_seconds=86_400),
                )
            )
        network_adapters.extend(
            [
                (
                    YahooResearchAdapter(values.get("YFINANCE_CACHE_DIR")),
                    ProviderPolicy(cost_tier="free", ttl_seconds=1_800),
                ),
                (
                    EcbFxAdapter(client=ResilientHttpTransport(policy)),
                    ProviderPolicy(cost_tier="free", ttl_seconds=86_400),
                ),
                (
                    OfficialPolicyWebAdapter(client=ResilientHttpTransport(policy)),
                    ProviderPolicy(cost_tier="free", ttl_seconds=21_600),
                ),
            ]
        )
        if values.get("TUSHARE_TOKEN"):
            network_adapters.append(
                (
                    TushareResearchAdapter(token=values.get("TUSHARE_TOKEN")),
                    ProviderPolicy(cost_tier="metered", ttl_seconds=86_400),
                )
            )
        cninfo_url = values.get("CNINFO_BASE_URL")
        raw_paths = values.get("CNINFO_DATASET_PATHS")
        if cninfo_url and raw_paths:
            network_adapters.append(
                (
                    CninfoAdapter(
                    base_url=cninfo_url,
                    dataset_paths={
                        DatasetKind(key): value
                        for key, value in json.loads(raw_paths).items()
                    },
                    headers=_cninfo_headers(values),
                    client=ResilientHttpTransport(policy),
                    ),
                    ProviderPolicy(cost_tier="metered", ttl_seconds=86_400),
                )
            )
    if enabled and _enabled("ENABLE_WIND", values):
        network_adapters.append(
            (WindResearchAdapter(), ProviderPolicy(cost_tier="paid", ttl_seconds=86_400))
        )
    if enabled and _enabled("ENABLE_IFIND", values):
        network_adapters.append(
            (IFindResearchAdapter(), ProviderPolicy(cost_tier="paid", ttl_seconds=86_400))
        )
    for adapter, provider_policy in network_adapters:
        if cache is None:
            if not offline and (
                provider_policy.cost_tier in {"free", "local"} or allow_paid
            ):
                adapters.append(adapter)
            continue
        adapters.append(
            CachedResearchSourceAdapter(
                adapter,
                cache,
                policy=provider_policy,
                offline=offline,
                refresh=refresh,
                allowed=(
                    provider_policy.cost_tier in {"free", "local"}
                    or allow_paid
                ),
                events=events,
            )
        )
    return CompositeResearchDataProvider(adapters)


def _enabled(name: str, values: Mapping[str, str] = os.environ) -> bool:
    return values.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _cninfo_headers(values: Mapping[str, str] = os.environ) -> dict[str, str]:
    token = values.get("CNINFO_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _float_env(
    name: str, default: float, values: Mapping[str, str] = os.environ
) -> float:
    try:
        return float(values.get(name, str(default)))
    except ValueError:
        return default


def _int_env(
    name: str, default: int, values: Mapping[str, str] = os.environ
) -> int:
    try:
        return max(1, int(values.get(name, str(default))))
    except ValueError:
        return default
