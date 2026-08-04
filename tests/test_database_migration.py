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


def test_d4f_70d_migration_is_additive():
    sql = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "002_d4f_70d.sql"
    ).read_text(encoding="utf-8").lower()

    assert "drop table" not in sql
    assert "create table if not exists llm_invocations" in sql
    assert "create table if not exists intraday_market_bars" in sql
    assert "add column if not exists error_message" in sql


def test_interactive_cli_cache_migration_is_additive_and_indexed():
    sql = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "003_interactive_cli_cache.sql"
    ).read_text(encoding="utf-8").lower()

    assert "drop table" not in sql
    assert "create table if not exists schema_migrations" in sql
    assert "create table if not exists provider_response_cache" in sql
    assert "add column if not exists external_ids_json" in sql
    assert "idx_provider_cache_lookup" in sql
