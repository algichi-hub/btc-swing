-- V5 F3: durable cycle journal with one logical five-minute slot per execution.
-- Applied only after 0001_initial, on Preview first.
CREATE TABLE IF NOT EXISTS worker_cycles (
    cycle_key TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','OK','ERROR')),
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    error_code TEXT,
    duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0)
);
CREATE INDEX IF NOT EXISTS idx_worker_cycles_started ON worker_cycles(started_at DESC);