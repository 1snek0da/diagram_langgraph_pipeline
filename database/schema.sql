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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    publisher TEXT,
    author TEXT,
    published_at TIMESTAMPTZ,
    url TEXT,
    file_path TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    industry_id UUID NOT NULL REFERENCES industries(id),
    as_of_date DATE NOT NULL,
    investment_horizon TEXT NOT NULL CHECK (investment_horizon IN ('short', 'medium', 'long')),
    user_request TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 2 CHECK (max_retries >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
    capex_period TEXT NOT NULL,
    capex_amount NUMERIC(30,4),
    capex_change_pct NUMERIC(14,8),
    capex_direction TEXT CHECK (capex_direction IN ('up', 'flat', 'down', 'unknown')),
    source_document_id UUID REFERENCES source_documents(id),
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, scenario_name)
);

CREATE TABLE company_business_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    business_summary TEXT,
    revenue_segments_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    industry_linkage TEXT,
    growth_driver_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE profit_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL REFERENCES securities(ticker),
    forecast_year INTEGER NOT NULL,
    revenue_forecast NUMERIC(30,4),
    net_profit_forecast NUMERIC(30,4),
    eps_forecast NUMERIC(20,8),
    pe_assumption NUMERIC(20,6),
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
    event_type TEXT NOT NULL,
    event_summary TEXT NOT NULL,
    impact_direction TEXT CHECK (impact_direction IN ('positive', 'neutral', 'negative')),
    impact_horizon TEXT,
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
CREATE INDEX idx_valuation_ticker_date ON market_valuation_metrics (ticker, trade_date DESC);
CREATE INDEX idx_evidence_run_type ON evidence_items (run_id, evidence_type);
CREATE INDEX idx_node_runs_run_status ON node_runs (run_id, status);
CREATE INDEX idx_capex_industry_period ON upstream_capex_records (industry_id, capex_period);
