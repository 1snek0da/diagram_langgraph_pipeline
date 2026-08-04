"""Runtime dependency bundle injected into every node factory."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import (
    AnalysisRepository,
    LanguageModelProvider,
    MarketDataProvider,
    ResearchDataProvider,
)
from .providers.factory import build_research_provider
from .providers.llm_factory import build_optional_llm_provider
from .providers.null_repository import NullRepository
from .events import NullEventSink
from .contracts import RunEventSink


@dataclass(frozen=True)
class AgentDependencies:
    market_data: MarketDataProvider
    research: ResearchDataProvider = field(default_factory=build_research_provider)
    repository: AnalysisRepository = field(default_factory=NullRepository)
    llm: LanguageModelProvider | None = field(
        default_factory=build_optional_llm_provider
    )
    events: RunEventSink = field(default_factory=NullEventSink)
