"""Data-provider implementations for the research graph."""

from .cninfo import CninfoAdapter
from .composite_research import CompositeResearchDataProvider
from .ecb_fx import EcbFxAdapter
from .factory import build_research_provider
from .in_memory_market import InMemoryMarketDataProvider
from .input_research import InputResearchProvider
from .http_transport import HttpPolicy, ResilientHttpTransport
from .licensed_reports import LicensedReportDirectoryAdapter
from .null_repository import NullRepository
from .policy_web import OfficialPolicyWebAdapter
from .sec_edgar import SecEdgarAdapter
from .tushare_research import TushareResearchAdapter
from .vendor_plugins import IFindResearchAdapter, WindResearchAdapter

__all__ = [
    "CninfoAdapter",
    "CompositeResearchDataProvider",
    "EcbFxAdapter",
    "IFindResearchAdapter",
    "InMemoryMarketDataProvider",
    "InputResearchProvider",
    "LicensedReportDirectoryAdapter",
    "NullRepository",
    "OfficialPolicyWebAdapter",
    "SecEdgarAdapter",
    "TushareResearchAdapter",
    "WindResearchAdapter",
    "HttpPolicy",
    "ResilientHttpTransport",
    "build_research_provider",
]
