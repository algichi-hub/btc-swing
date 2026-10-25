-- G6 manual refresh: durable command queue (Preview applied 2026-10-25).
-- API only inserts/reads commands; Engine worker alone executes official cycles.
-- Run as the migration owner in the intended Neon branch.
CREATE TABLE IF NOT EXISTS public.manual_cycle_requests (
    id text PRIMARY KEY,
    status text NOT NULL DEFAULT 'PENDING'
      CHECK (status IN ('PENDING', 'RUNNING', 'OK', 'ERROR')),
    requested_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    snapshot_id bigint,
    snapshot_at text
);
CREATE UNIQUE INDEX IF NOT EXISTS manual_cycle_one_active
    ON public.manual_cycle_requests ((true))
    WHERE status IN ('PENDING', 'RUNNING');
GRANT SELECT, INSERT ON public.manual_cycle_requests TO btc_v5_web_app;
GRANT SELECT, UPDATE ON public.manual_cycle_requests TO btc_v5_engine_app;
