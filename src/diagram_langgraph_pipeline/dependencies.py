"""Runtime dependency bundle injected into every node factory."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import AnalysisRepository, MarketDataProvider, ResearchDataProvider
from .providers.input_research import InputResearchProvider
from .providers.null_repository import NullRepository


@dataclass(frozen=True)
class AgentDependencies:
    market_data: MarketDataProvider
    research: ResearchDataProvider = InputResearchProvider()
    repository: AnalysisRepository = NullRepository()
