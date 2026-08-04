-- Additive cache and migration ledger for the interactive DB-first CLI.
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE securities
    ADD COLUMN IF NOT EXISTS external_ids_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS provider_response_cache (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    dataset_kind TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    cache_as_of_date DATE NOT NULL,
    coverage_start DATE,
    coverage_end DATE,
    status TEXT NOT NULL CHECK (
        status IN ('completed', 'partial', 'failed', 'unavailable')
    ),
    coverage_ratio NUMERIC(8,6),
    schema_version INTEGER NOT NULL DEFAULT 1,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, dataset_kind, scope_hash, cache_as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_provider_cache_lookup
    ON provider_response_cache
    (provider, dataset_kind, scope_hash, cache_as_of_date DESC, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_provider_cache_expiry
    ON provider_response_cache (expires_at);
CREATE INDEX IF NOT EXISTS idx_securities_external_ids
    ON securities USING GIN (external_ids_json);

COMMIT;
