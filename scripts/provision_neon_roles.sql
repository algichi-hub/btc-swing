-- F2 least-privilege roles. Initial credentials are intentionally NULL.
-- Set passwords securely in Railway/Neon at F3/F4; never commit credentials.
-- Run with the schema owner on each Neon branch, after 0001_initial.sql.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='btc_v5_engine_app') THEN
        CREATE ROLE btc_v5_engine_app LOGIN PASSWORD NULL NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='btc_v5_web_app') THEN
        CREATE ROLE btc_v5_web_app LOGIN PASSWORD NULL NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT;
    END IF;
END $$;
-- Connect privilege is granted separately per database during deployment.
GRANT USAGE ON SCHEMA public TO btc_v5_engine_app, btc_v5_web_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    trade_opportunities, trade_signals, trade_events, trade_results,
    telegram_events, engine_runtime_state, engine_snapshots, notification_outbox,
    operational_logs, worker_heartbeat
TO btc_v5_engine_app;
GRANT SELECT ON app_settings, push_subscriptions TO btc_v5_engine_app;
GRANT USAGE, SELECT ON SEQUENCE
    trade_signals_id_seq, trade_events_id_seq, telegram_events_id_seq,
    engine_snapshots_id_seq, notification_outbox_id_seq, operational_logs_id_seq
TO btc_v5_engine_app;
GRANT SELECT ON
    trade_opportunities, trade_signals, trade_events, trade_results,
    engine_runtime_state, engine_snapshots, operational_logs, worker_heartbeat,
    notification_outbox, telegram_events
TO btc_v5_web_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    users, auth_sessions, auth_login_attempts, auth_recovery_codes, app_settings, push_subscriptions
TO btc_v5_web_app;
GRANT USAGE, SELECT ON SEQUENCE
    users_id_seq, auth_sessions_id_seq, auth_login_attempts_id_seq,
    push_subscriptions_id_seq
TO btc_v5_web_app;