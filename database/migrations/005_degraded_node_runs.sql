-- Allow optional analysis nodes to finish in a degraded or skipped state.
BEGIN;

ALTER TABLE node_runs DROP CONSTRAINT IF EXISTS node_runs_status_check;
ALTER TABLE node_runs ADD CONSTRAINT node_runs_status_check
CHECK (status IN ('pending','running','completed','degraded','failed','skipped'));

COMMIT;
