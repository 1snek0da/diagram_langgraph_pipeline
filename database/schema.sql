-- PostgreSQL 15+ schema for the standalone LangGraph research pipeline.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE industries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    industry_name TEXT NOT NULL,
    parent_industry_id UUID REFERENCES industries(id),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (industry_name, parent_industry_id)
);

CREATE TABLE securities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    market TEXT NOT NULL,
    exchange TEXT NOT NULL,
    industry_id UUID REFERENCES industries(id),
    external_ids_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE provider_response_cache (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    dataset_kind TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    cache_as_of_date DATE NOT NULL,
    coverage_start DATE,
    coverage_end DATE,
    status TEXT NOT NULL CHECK (status IN ('completed', 'partial', 'failed', 'unavailable')),
    coverage_ratio NUMERIC(8,6),
    schema_version INTEGER NOT NULL DEFAULT 1,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, dataset_kind, scope_hash, cache_as_of_date)
);

CREATE TABLE source_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    source_tier TEXT NOT NULL,
    source_type TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    publisher TEXT,
    author TEXT,
    published_at TIMESTAMPTZ,
    url TEXT,
    file_path TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    language TEXT,
    license_scope TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    industry_id UUID NOT NULL REFERENCES industries(id),
    as_of_date DATE NOT NULL,
    investment_horizon TEXT NOT NULL CHECK (investment_horizon IN ('short', 'medium', 'long')),
    task_type TEXT NOT NULL DEFAULT 'full',
    user_request TEXT,
    status TEXT NOT NULL CONSTRAINT analysis_runs_status_check CHECK (
        status IN ('pending', 'running', 'completed', 'degraded', 'failed', 'interrupted')
    ),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 2 CHECK (max_retries >= 0),
    error_code TEXT,
    error_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE provider_fetch_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    dataset_kind TEXT NOT NULL,
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'partial', 'failed', 'unavailable')),
    coverage_ratio NUMERIC(8,6) CHECK (coverage_ratio BETWEEN 0 AND 1),
    warning_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ
);

CREATE TABLE node_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    error_message TEXT,
    input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, node_name, attempt_no)
);

CREATE TABLE evidence_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES source_documents(id),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT REFERENCES securities(ticker),
    industry_id UUID REFERENCES industries(id),
    evidence_type TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    extracted_value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    page_no INTEGER,
    paragraph_ref TEXT,
    metric_key TEXT,
    extraction_method TEXT NOT NULL DEFAULT 'provided',
    quote_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE market_bars (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    trade_date DATE NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly')),
    open_price NUMERIC(24,8),
    high_price NUMERIC(24,8),
    low_price NUMERIC(24,8),
    close_price NUMERIC(24,8) NOT NULL,
    adj_close_price NUMERIC(24,8),
    volume NUMERIC(30,4),
    turnover_amount NUMERIC(30,4),
    turnover_rate NUMERIC(14,8),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticker, trade_date, frequency, source)
);

CREATE TABLE market_valuation_metrics (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    trade_date DATE NOT NULL,
    pe_ttm NUMERIC(20,6),
    pb NUMERIC(20,6),
    ps_ttm NUMERIC(20,6),
    dividend_yield NUMERIC(14,8),
    market_cap NUMERIC(30,4),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticker, trade_date, source)
);

CREATE TABLE intraday_market_bars (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID REFERENCES analysis_runs(id) ON DELETE SET NULL,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    bar_time TIMESTAMPTZ NOT NULL,
    interval TEXT NOT NULL,
    open_price NUMERIC(24,8),
    high_price NUMERIC(24,8),
    low_price NUMERIC(24,8),
    close_price NUMERIC(24,8) NOT NULL,
    adj_close_price NUMERIC(24,8),
    volume NUMERIC(30,4),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticker, bar_time, interval, source)
);

CREATE TABLE llm_invocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    provider TEXT,
    model TEXT,
    request_id TEXT,
    input_hash TEXT NOT NULL,
    candidate_char_count BIGINT NOT NULL,
    projected_char_count BIGINT NOT NULL,
    estimated_prompt_tokens BIGINT NOT NULL,
    prompt_tokens BIGINT,
    completion_tokens BIGINT,
    cached_tokens BIGINT,
    usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    projection_manifest_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_type TEXT,
    error_message TEXT,
    cache_hit BOOLEAN NOT NULL DEFAULT false,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    UNIQUE (run_id, node_name, attempt_no)
);

CREATE TABLE stock_market_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    analysis_window TEXT NOT NULL,
    return_5d NUMERIC(14,8),
    return_20d NUMERIC(14,8),
    return_60d NUMERIC(14,8),
    return_120d NUMERIC(14,8),
    return_250d NUMERIC(14,8),
    volatility_20d NUMERIC(14,8),
    max_drawdown NUMERIC(14,8),
    atr_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ma_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    volume_price_signal JSONB NOT NULL DEFAULT '{}'::jsonb,
    valuation_percentile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    relative_strength_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    abnormal_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE industry_analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    industry_id UUID NOT NULL REFERENCES industries(id),
    summary TEXT,
    growth_view TEXT,
    policy_view TEXT,
    technology_view TEXT,
    capex_view TEXT,
    valuation_view TEXT,
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE upstream_capex_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    industry_id UUID NOT NULL REFERENCES industries(id),
    company_name TEXT NOT NULL,
    entity_id TEXT,
    company_role TEXT CHECK (company_role IN ('demand', 'supply', 'other')),
    fiscal_year INTEGER,
    capex_period TEXT NOT NULL,
    capex_amount NUMERIC(30,4),
    communication_capex_amount NUMERIC(30,4),
    currency CHAR(3),
    unit TEXT,
    scale NUMERIC(30,8) NOT NULL DEFAULT 1,
    fact_basis TEXT CHECK (fact_basis IN ('reported', 'extracted', 'estimated', 'derived')),
    provider TEXT,
    capex_change_pct NUMERIC(14,8),
    capex_direction TEXT CHECK (capex_direction IN ('up', 'flat', 'down', 'unknown')),
    source_document_id UUID REFERENCES source_documents(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE financial_metric_facts (
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
    fact_basis TEXT NOT NULL CHECK (fact_basis IN ('reported', 'extracted', 'estimated', 'derived')),
    provider TEXT NOT NULL,
    source_document_id UUID REFERENCES source_documents(id),
    observed_at TIMESTAMPTZ,
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id, metric_key, fiscal_year, period_end, provider, source_document_id)
);

CREATE TABLE capex_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    total_capex_fact_id UUID REFERENCES financial_metric_facts(id),
    communication_capex_fact_id UUID REFERENCES financial_metric_facts(id),
    communication_share NUMERIC(14,10),
    allocation_basis TEXT NOT NULL CHECK (allocation_basis IN ('reported', 'extracted', 'estimated', 'derived')),
    evidence_id UUID REFERENCES evidence_items(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, entity_id, fiscal_year)
);

CREATE TABLE capex_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    scenario_name TEXT NOT NULL CHECK (scenario_name IN ('bear', 'base', 'bull')),
    forecast_year INTEGER NOT NULL,
    communication_capex NUMERIC(38,10),
    currency CHAR(3),
    growth_rate NUMERIC(18,10),
    communication_share NUMERIC(14,10),
    forecast_method TEXT NOT NULL,
    formula_version TEXT NOT NULL,
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    assumptions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, scenario_name, forecast_year)
);

CREATE TABLE policy_impact_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK (direction IN ('positive', 'neutral', 'negative')),
    magnitude TEXT NOT NULL CHECK (magnitude IN ('small', 'large', 'unknown')),
    impact_horizon TEXT,
    affected_metrics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    quantified_impact_pct NUMERIC(18,10),
    evidence_id UUID REFERENCES evidence_items(id),
    model_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE industry_valuation_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    industry_id UUID NOT NULL REFERENCES industries(id),
    scenario_name TEXT NOT NULL,
    future_profit NUMERIC(30,4),
    future_revenue NUMERIC(30,4),
    assumed_pe NUMERIC(20,6),
    assumed_ps NUMERIC(20,6),
    estimated_market_cap NUMERIC(30,4),
    current_market_cap NUMERIC(30,4),
    upside_pct NUMERIC(14,8),
    assumptions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    original_currency CHAR(3),
    fx_rate NUMERIC(24,12),
    fx_rate_date DATE,
    formula_version TEXT,
    universe_id TEXT,
    universe_as_of_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, scenario_name)
);

CREATE TABLE company_business_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    business_summary TEXT,
    company_type TEXT,
    market_share_rank INTEGER,
    base_pe_low NUMERIC(20,6),
    base_pe_high NUMERIC(20,6),
    revenue_segments_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    industry_linkage TEXT,
    growth_driver_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE company_classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    company_type TEXT NOT NULL CHECK (
        company_type IN ('optical_chip', 'optical_module', 'optical_component', 'communication_equipment', 'pcb_connector', 'unknown')
    ),
    market_share_rank INTEGER CHECK (market_share_rank > 0),
    industry_position TEXT CHECK (industry_position IN ('leader', 'second_tier', 'lower_tier', 'unknown')),
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

CREATE TABLE profit_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    forecast_year INTEGER NOT NULL,
    institution TEXT,
    published_at TIMESTAMPTZ,
    forecast_basis TEXT,
    currency CHAR(3),
    revenue_forecast NUMERIC(30,4),
    net_profit_forecast NUMERIC(30,4),
    eps_forecast NUMERIC(20,8),
    pe_assumption NUMERIC(20,6),
    revision_pct NUMERIC(18,10),
    source_type TEXT,
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    source_document_id UUID REFERENCES source_documents(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE marginal_change_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    event_date DATE,
    published_at TIMESTAMPTZ,
    event_type TEXT NOT NULL,
    event_summary TEXT NOT NULL,
    impact_direction TEXT CHECK (impact_direction IN ('positive', 'neutral', 'negative')),
    impact_horizon TEXT,
    certainty TEXT CHECK (certainty IN ('low', 'medium', 'high')),
    source_document_id UUID REFERENCES source_documents(id),
    evidence_id UUID REFERENCES evidence_items(id),
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE company_valuation_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    scenario_name TEXT NOT NULL,
    forecast_profit NUMERIC(30,4),
    assumed_pe NUMERIC(20,6),
    estimated_market_cap NUMERIC(30,4),
    current_market_cap NUMERIC(30,4),
    upside_pct NUMERIC(14,8),
    downside_pct NUMERIC(14,8),
    assumptions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, scenario_name)
);

CREATE TABLE market_index_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    index_code TEXT NOT NULL,
    trend_view TEXT,
    valuation_position TEXT,
    risk_preference TEXT,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE technical_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK (target_type IN ('stock', 'sector', 'index')),
    target_code TEXT NOT NULL,
    trend TEXT,
    support_price NUMERIC(24,8),
    resistance_price NUMERIC(24,8),
    volume_signal TEXT,
    pattern_name TEXT,
    cycle_position TEXT,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, target_type, target_code)
);

CREATE TABLE sentiment_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    industry_id UUID NOT NULL REFERENCES industries(id),
    sentiment_score NUMERIC(8,6),
    heat_score NUMERIC(8,6),
    crowding_risk TEXT,
    positive_items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    negative_items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE decision_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    stock_market_analysis_id UUID NOT NULL REFERENCES stock_market_analysis(id),
    action_bias TEXT NOT NULL CHECK (action_bias IN ('buy', 'hold', 'watch', 'reduce', 'sell')),
    conviction TEXT NOT NULL CHECK (conviction IN ('low', 'medium', 'high')),
    buy_zone JSONB NOT NULL DEFAULT '{}'::jsonb,
    sell_zone JSONB NOT NULL DEFAULT '{}'::jsonb,
    invalid_condition TEXT,
    supporting_points_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_points_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence_score NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE decision_evidence_links (
    decision_id UUID NOT NULL REFERENCES decision_records(id) ON DELETE CASCADE,
    evidence_id UUID NOT NULL REFERENCES evidence_items(id),
    relationship TEXT NOT NULL CHECK (relationship IN ('support', 'risk', 'conflict')),
    PRIMARY KEY (decision_id, evidence_id, relationship)
);

CREATE TABLE decision_node_links (
    decision_id UUID NOT NULL REFERENCES decision_records(id) ON DELETE CASCADE,
    node_run_id UUID NOT NULL REFERENCES node_runs(id),
    PRIMARY KEY (decision_id, node_run_id)
);

CREATE TABLE review_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    passed BOOLEAN NOT NULL,
    completeness_score NUMERIC(5,4),
    evidence_score NUMERIC(5,4),
    logic_score NUMERIC(5,4),
    missing_items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    retry_tasks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    review_comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, attempt_no)
);

CREATE TABLE final_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    report_markdown TEXT NOT NULL,
    report_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_market_bars_ticker_date ON market_bars (ticker, trade_date DESC);
CREATE INDEX idx_provider_cache_lookup ON provider_response_cache
    (provider, dataset_kind, scope_hash, cache_as_of_date DESC, expires_at DESC);
CREATE INDEX idx_provider_cache_expiry ON provider_response_cache (expires_at);
CREATE INDEX idx_securities_external_ids ON securities USING GIN (external_ids_json);
CREATE INDEX idx_intraday_market_bars_ticker_time ON intraday_market_bars (ticker, bar_time DESC);
CREATE INDEX idx_llm_invocations_run_node ON llm_invocations (run_id, node_name, attempt_no);
CREATE INDEX idx_valuation_ticker_date ON market_valuation_metrics (ticker, trade_date DESC);
CREATE INDEX idx_evidence_run_type ON evidence_items (run_id, evidence_type);
CREATE INDEX idx_node_runs_run_status ON node_runs (run_id, status);
CREATE INDEX idx_capex_industry_period ON upstream_capex_records (industry_id, capex_period);
CREATE INDEX idx_provider_fetch_run ON provider_fetch_runs (run_id, provider, dataset_kind);
CREATE INDEX idx_metric_fact_lookup ON financial_metric_facts (entity_id, metric_key, fiscal_year DESC);
CREATE INDEX idx_capex_forecast_run_year ON capex_forecasts (run_id, forecast_year);
CREATE INDEX idx_profit_forecast_asof ON profit_forecasts (ticker, published_at, forecast_year);
CREATE INDEX idx_analysis_runs_web_history
    ON analysis_runs (created_at DESC, task_type, status, ticker);
