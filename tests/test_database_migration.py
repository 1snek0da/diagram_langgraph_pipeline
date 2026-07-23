from pathlib import Path


def test_research_source_migration_is_incremental_and_complete():
    sql = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "001_research_source_normalization.sql"
    ).read_text(encoding="utf-8").lower()

    assert "drop table" not in sql
    assert "alter table source_documents add column if not exists provider" in sql
    for table in (
        "provider_fetch_runs",
        "financial_metric_facts",
        "capex_allocations",
        "capex_forecasts",
        "policy_impact_assessments",
        "company_classifications",
    ):
        assert f"create table if not exists {table}" in sql
