-- Extend persisted analysis runs for the web lifecycle and history APIs.
BEGIN;

ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS task_type TEXT NOT NULL DEFAULT 'full';
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS error_code TEXT;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS error_summary TEXT;

ALTER TABLE analysis_runs DROP CONSTRAINT IF EXISTS analysis_runs_status_check;
ALTER TABLE analysis_runs ADD CONSTRAINT analysis_runs_status_check
CHECK (status IN ('pending','running','completed','degraded','failed','interrupted'));

CREATE INDEX IF NOT EXISTS idx_analysis_runs_web_history
ON analysis_runs (created_at DESC, task_type, status, ticker);

COMMIT;
