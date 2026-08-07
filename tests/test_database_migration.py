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


def test_web_api_migration_extends_analysis_lifecycle():
    sql = Path("database/migrations/004_web_analysis_api.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "add column if not exists task_type" in sql
    assert "add column if not exists error_code" in sql
    assert "add column if not exists error_summary" in sql
    assert "'degraded'" in sql
    assert "'interrupted'" in sql
    assert "idx_analysis_runs_web_history" in sql
