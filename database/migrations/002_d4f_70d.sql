-- Additive persistence for the d4f_70d profile.
CREATE TABLE IF NOT EXISTS intraday_market_bars (
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

CREATE TABLE IF NOT EXISTS llm_invocations (
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

ALTER TABLE llm_invocations ADD COLUMN IF NOT EXISTS error_message TEXT;

CREATE INDEX IF NOT EXISTS idx_intraday_market_bars_ticker_time
    ON intraday_market_bars (ticker, bar_time DESC);
CREATE INDEX IF NOT EXISTS idx_llm_invocations_run_node
    ON llm_invocations (run_id, node_name, attempt_no);
