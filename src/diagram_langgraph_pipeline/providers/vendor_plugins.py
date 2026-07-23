"""Runtime plugin wrappers for licensed Wind and iFinD installations."""

from __future__ import annotations

from importlib.util import find_spec
from typing import Callable

from ..schemas.research import DatasetKind, SourceBatch, SourceRequest


VendorFetcher = Callable[[SourceRequest], SourceBatch]


class _VendorPluginAdapter:
    module_name = ""
    vendor_name = ""
    capabilities = frozenset(DatasetKind)

    def __init__(self, fetcher: VendorFetcher | None = None):
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return self.vendor_name

    def fetch(self, request: SourceRequest) -> SourceBatch:
        if find_spec(self.module_name) is None:
            return SourceBatch(errors=[f"{self.vendor_name} SDK is not installed"])
        if self._fetcher is None:
            return SourceBatch(errors=[f"{self.vendor_name} SDK is installed but no licensed query mapping is configured"])
        result = self._fetcher(request)
        return result if isinstance(result, SourceBatch) else SourceBatch.model_validate(result)


class WindResearchAdapter(_VendorPluginAdapter):
    module_name = "WindPy"
    vendor_name = "wind"


class IFindResearchAdapter(_VendorPluginAdapter):
    module_name = "iFinDPy"
    vendor_name = "ifind"
