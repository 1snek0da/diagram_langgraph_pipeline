"""Environment-driven registration of optional research adapters."""

from __future__ import annotations

import json
import os

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


def build_research_provider() -> CompositeResearchDataProvider:
    """Build a provider that stays fully offline unless explicitly enabled."""

    report_roots = [item for item in os.getenv("LICENSED_REPORT_DIRS", "").split(os.pathsep) if item]
    adapters = [InputResearchProvider(), LicensedReportDirectoryAdapter(report_roots)]
    if _enabled("ENABLE_NETWORK_RESEARCH"):
        policy = HttpPolicy(
            timeout_seconds=_float_env("PROVIDER_TIMEOUT_SECONDS", 20.0),
            max_attempts=_int_env("PROVIDER_MAX_ATTEMPTS", 3),
            minimum_interval_seconds=_float_env("PROVIDER_MIN_INTERVAL_SECONDS", 0.1),
        )
        user_agent = os.getenv("SEC_USER_AGENT", "")
        if "@" in user_agent:
            adapters.append(SecEdgarAdapter(user_agent=user_agent, client=ResilientHttpTransport(policy)))
        adapters.extend(
            [
                EcbFxAdapter(client=ResilientHttpTransport(policy)),
                OfficialPolicyWebAdapter(client=ResilientHttpTransport(policy)),
            ]
        )
        if os.getenv("TUSHARE_TOKEN"):
            adapters.append(TushareResearchAdapter())
        cninfo_url = os.getenv("CNINFO_BASE_URL")
        raw_paths = os.getenv("CNINFO_DATASET_PATHS")
        if cninfo_url and raw_paths:
            adapters.append(
                CninfoAdapter(
                    base_url=cninfo_url,
                    dataset_paths={
                        DatasetKind(key): value
                        for key, value in json.loads(raw_paths).items()
                    },
                    headers=_cninfo_headers(),
                    client=ResilientHttpTransport(policy),
                )
            )
    if _enabled("ENABLE_WIND"):
        adapters.append(WindResearchAdapter())
    if _enabled("ENABLE_IFIND"):
        adapters.append(IFindResearchAdapter())
    return CompositeResearchDataProvider(adapters)


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _cninfo_headers() -> dict[str, str]:
    token = os.getenv("CNINFO_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default
