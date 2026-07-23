-- Incremental migration: typed research sources, CapEx forecasts and company classifications.
BEGIN;

ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS provider TEXT;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS source_tier TEXT;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS external_id TEXT;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS license_scope TEXT;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS paragraph_ref TEXT;
ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS metric_key TEXT;
ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS extraction_method TEXT NOT NULL DEFAULT 'provided';

ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS entity_id TEXT;
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS company_role TEXT;
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS fiscal_year INTEGER;
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS communication_capex_amount NUMERIC(30,4);
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS currency CHAR(3);
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS unit TEXT;
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS scale NUMERIC(30,8) NOT NULL DEFAULT 1;
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS fact_basis TEXT;
ALTER TABLE upstream_capex_records ADD COLUMN IF NOT EXISTS provider TEXT;

ALTER TABLE industry_valuation_scenarios ADD COLUMN IF NOT EXISTS original_currency CHAR(3);
ALTER TABLE industry_valuation_scenarios ADD COLUMN IF NOT EXISTS fx_rate NUMERIC(24,12);
ALTER TABLE industry_valuation_scenarios ADD COLUMN IF NOT EXISTS fx_rate_date DATE;
ALTER TABLE industry_valuation_scenarios ADD COLUMN IF NOT EXISTS formula_version TEXT;
ALTER TABLE industry_valuation_scenarios ADD COLUMN IF NOT EXISTS universe_id TEXT;
ALTER TABLE industry_valuation_scenarios ADD COLUMN IF NOT EXISTS universe_as_of_date DATE;

ALTER TABLE company_business_profiles ADD COLUMN IF NOT EXISTS company_type TEXT;
ALTER TABLE company_business_profiles ADD COLUMN IF NOT EXISTS market_share_rank INTEGER;
ALTER TABLE company_business_profiles ADD COLUMN IF NOT EXISTS base_pe_low NUMERIC(20,6);
ALTER TABLE company_business_profiles ADD COLUMN IF NOT EXISTS base_pe_high NUMERIC(20,6);

ALTER TABLE profit_forecasts ADD COLUMN IF NOT EXISTS institution TEXT;
ALTER TABLE profit_forecasts ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
ALTER TABLE profit_forecasts ADD COLUMN IF NOT EXISTS forecast_basis TEXT;
ALTER TABLE profit_forecasts ADD COLUMN IF NOT EXISTS currency CHAR(3);
ALTER TABLE profit_forecasts ADD COLUMN IF NOT EXISTS revision_pct NUMERIC(18,10);

ALTER TABLE marginal_change_events ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
ALTER TABLE marginal_change_events ADD COLUMN IF NOT EXISTS certainty TEXT;
ALTER TABLE marginal_change_events ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES source_documents(id);

CREATE TABLE IF NOT EXISTS provider_fetch_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    dataset_kind TEXT NOT NULL,
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    coverage_ratio NUMERIC(8,6),
    warning_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS financial_metric_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    ticker TEXT REFERENCES securities(ticker),
    fiscal_year INTEGER,
    period_start DATE,
    period_end DATE,
    value NUMERIC(38,10),
    currency CHAR(3),
    unit TEXT NOT NULL,
    scale NUMERIC(30,8) NOT NULL DEFAULT 1,
    fact_basis TEXT NOT NULL,
    provider TEXT NOT NULL,
    source_document_id UUID REFERENCES source_documents(id),
    observed_at TIMESTAMPTZ,
    confidence_score NUMERIC(5,4),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, metric_key, fiscal_year, period_end, provider, source_document_id)
);

CREATE TABLE IF NOT EXISTS capex_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    total_capex_fact_id UUID REFERENCES financial_metric_facts(id),
    communication_capex_fact_id UUID REFERENCES financial_metric_facts(id),
    communication_share NUMERIC(14,10),
    allocation_basis TEXT NOT NULL,
    evidence_id UUID REFERENCES evidence_items(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, entity_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS capex_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    scenario_name TEXT NOT NULL,
    forecast_year INTEGER NOT NULL,
    communication_capex NUMERIC(38,10),
    currency CHAR(3),
    growth_rate NUMERIC(18,10),
    communication_share NUMERIC(14,10),
    forecast_method TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    confidence_score NUMERIC(5,4),
    assumptions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, scenario_name, forecast_year)
);

CREATE TABLE IF NOT EXISTS policy_impact_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    direction TEXT NOT NULL,
    magnitude TEXT NOT NULL,
    impact_horizon TEXT,
    affected_metrics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    quantified_impact_pct NUMERIC(18,10),
    evidence_id UUID REFERENCES evidence_items(id),
    model_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS company_classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    company_type TEXT NOT NULL,
    market_share_rank INTEGER,
    industry_position TEXT,
    base_pe_low NUMERIC(20,6),
    base_pe_high NUMERIC(20,6),
    adjustment_low NUMERIC(12,8),
    adjustment_high NUMERIC(12,8),
    final_pe_low NUMERIC(20,6),
    final_pe_high NUMERIC(20,6),
    evidence_id UUID REFERENCES evidence_items(id),
    model_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_provider_fetch_run ON provider_fetch_runs (run_id, provider, dataset_kind);
CREATE INDEX IF NOT EXISTS idx_metric_fact_lookup ON financial_metric_facts (entity_id, metric_key, fiscal_year DESC);
CREATE INDEX IF NOT EXISTS idx_capex_forecast_run_year ON capex_forecasts (run_id, forecast_year);
CREATE INDEX IF NOT EXISTS idx_profit_forecast_asof ON profit_forecasts (ticker, published_at, forecast_year);

COMMIT;
