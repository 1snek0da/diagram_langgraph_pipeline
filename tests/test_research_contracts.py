from datetime import date
from decimal import Decimal

from diagram_langgraph_pipeline.providers import CompositeResearchDataProvider
from diagram_langgraph_pipeline.schemas import (
    CoverageReport,
    DatasetKind,
    FactBasis,
    MetricFact,
    SourceBatch,
    SourceRequest,
)


def _request(kind=DatasetKind.CAPEX):
    return SourceRequest(
        dataset_kind=kind,
        run_id="test-run",
        as_of_date=date(2026, 7, 21),
        forecast_years=[2027, 2028],
    )


def test_coverage_counts_only_requested_items():
    coverage = CoverageReport.from_items(["a", "b"], ["a", "unrequested"])

    assert coverage.coverage_ratio == Decimal("0.5")
    assert coverage.missing_items == ["b"]


def test_composite_isolates_provider_failure_and_deduplicates_facts():
    fact = MetricFact(
        metric_key="total_capex",
        entity_id="alphabet",
        fiscal_year=2025,
        value=Decimal("100"),
        currency="USD",
        unit="currency",
        basis=FactBasis.REPORTED,
        provider="official",
    )

    class Good:
        name = "good"
        capabilities = frozenset({DatasetKind.CAPEX})

        def fetch(self, request):
            return SourceBatch(
                facts=[fact, fact.model_copy()],
                coverage=CoverageReport.from_items(["alphabet"], ["alphabet"]),
            )

    class Bad:
        name = "bad"
        capabilities = frozenset({DatasetKind.CAPEX})

        def fetch(self, request):
            raise RuntimeError("temporary failure")

    batch = CompositeResearchDataProvider([Good(), Bad()]).fetch(_request())

    assert len(batch.facts) == 1
    assert batch.data["records"][0]["total_capex"] == Decimal("100")
    assert any("bad: RuntimeError" in item for item in batch.errors)
    assert batch.coverage.coverage_ratio == Decimal("1")
