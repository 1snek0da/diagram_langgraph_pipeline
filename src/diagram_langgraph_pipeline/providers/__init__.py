"""Data-provider implementations for the research graph."""

from .cninfo import CninfoAdapter
from .composite_research import CompositeResearchDataProvider
from .ecb_fx import EcbFxAdapter
from .factory import build_research_provider
from .in_memory_market import InMemoryMarketDataProvider
from .input_research import InputResearchProvider
from .http_transport import HttpPolicy, ResilientHttpTransport
from .licensed_reports import LicensedReportDirectoryAdapter
from .llm_factory import build_optional_llm_provider
from .null_repository import NullRepository
from .policy_web import OfficialPolicyWebAdapter
from .postgres_repository import PostgresAnalysisRepository
from .sec_edgar import SecEdgarAdapter
from .tushare_research import TushareResearchAdapter
from .volcengine_llm import (
    VolcengineChatClient,
    VolcengineLLMConfig,
    VolcengineLLMError,
)
from .vendor_plugins import IFindResearchAdapter, WindResearchAdapter
from .cache import CachedResearchSourceAdapter, DatabaseFirstMarketDataProvider
from .yahoo_research import YahooResearchAdapter
from .yfinance_market import YFinanceMarketDataProvider

__all__ = [
    "CninfoAdapter",
    "CompositeResearchDataProvider",
    "EcbFxAdapter",
    "IFindResearchAdapter",
    "InMemoryMarketDataProvider",
    "InputResearchProvider",
    "LicensedReportDirectoryAdapter",
    "build_optional_llm_provider",
    "NullRepository",
    "OfficialPolicyWebAdapter",
    "PostgresAnalysisRepository",
    "SecEdgarAdapter",
    "TushareResearchAdapter",
    "VolcengineChatClient",
    "VolcengineLLMConfig",
    "VolcengineLLMError",
    "WindResearchAdapter",
    "HttpPolicy",
    "ResilientHttpTransport",
    "build_research_provider",
    "CachedResearchSourceAdapter",
    "DatabaseFirstMarketDataProvider",
    "YahooResearchAdapter",
    "YFinanceMarketDataProvider",
]
