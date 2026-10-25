"""Durable single-logical-cycle worker for Railway and PostgreSQL.

This code doesn't place exchange orders. TradingAutomationEngine retains V4's
paper-trade behavior. Telegram remains disabled in F3; removed in F5.

An advisory *session* lock serializes workers; a durable cycle journal prevents
repeated successful cycles in the same UTC 300-second slot. A crash before the
cycle commits OK may cause a retry: downstream event inserts must be idempotent.
"""
from __future__ import annotations

import logging
import os
import re
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

LOCK_KEY = 5032026
INTERVAL_SECONDS = 300
SERVICE_KEY = 'btc-v5-engine'
_LOG = logging.getLogger('btc_v5.worker')


def cycle_key(now: datetime) -> str:
    """UTC floor to exact five-minute interval; unaffected by local DST."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Timezone-aware UTC instant required')
    slot = int(now.timestamp()) // INTERVAL_SECONDS * INTERVAL_SECONDS
    return datetime.fromtimestamp(slot, tz=timezone.utc).isoformat()


def _safe_error(error: BaseException | str) -> str:
    """Persist only a safe exception class/code, not messages containing credentials."""
    if isinstance(error, BaseException):
        return type(error).__name__[:64]
    value = str(error)
    return value if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value) else 'WorkerError'


def _connect():
    from app.storage.postgres import connect_pg
    return connect_pg()


def _telemetry(*, severity: str, code: str, key: str | None = None, message: str = '') -> None:
    # Never store raw provider errors or secrets in the user-visible log feed.
    with _connect() as conn:
        conn.execute('''INSERT INTO operational_logs(service,severity,cycle_key,code,message)
                        VALUES(%s,%s,%s,%s,%s)''',
                     (SERVICE_KEY, severity, key, code, message[:500]))


def _heartbeat(*, key: str | None, status: str, success: bool = False, details: str = '') -> None:
    with _connect() as conn:
        conn.execute('''INSERT INTO worker_heartbeat
                        (worker_key,last_seen_at,last_success_at,status,cycle_key,details)
                        VALUES(%s,now(),CASE WHEN %s THEN now() ELSE NULL END,%s,%s,%s)
                        ON CONFLICT(worker_key) DO UPDATE SET
                          last_seen_at=EXCLUDED.last_seen_at,
                          last_success_at=COALESCE(EXCLUDED.last_success_at,worker_heartbeat.last_success_at),
                          status=EXCLUDED.status,cycle_key=EXCLUDED.cycle_key,details=EXCLUDED.details''',
                     (SERVICE_KEY, success, status, key, details[:80]))


def get_worker_health(now: datetime | None = None, *, max_age_seconds: int = 660) -> dict:
    """Database-backed health for F4 UI. Never uses a process-local flag."""
    instant = now or datetime.now(timezone.utc)
    with _connect() as conn:
        row = conn.execute('''SELECT last_seen_at,last_success_at,status,cycle_key,details
                              FROM worker_heartbeat WHERE worker_key=%s''', (SERVICE_KEY,)).fetchone()
    if not row:
        return {'status':'SIN DATOS','last_seen_at':None,'last_success_at':None,'cycle_key':None}
    age = max(0., (instant-row['last_seen_at']).total_seconds())
    status = 'RETRASADO' if age > max_age_seconds else row['status']
    return {'status':status,'age_seconds':round(age,1),
            'last_seen_at':row['last_seen_at'].isoformat(),
            'last_success_at':row['last_success_at'].isoformat() if row['last_success_at'] else None,
            'cycle_key':row['cycle_key']}


def run_once(run_engine: Callable[[], object], *, now: datetime | None = None, manual_request_id: str | None = None) -> str:
    """Return OK, ERROR, SKIPPED or BUSY; serialize across processes and redeploys.

    Session lock survives commits from other repository connections, and is
    released upon process crash/connection termination.
    """
    if os.getenv('BTC_DB_BACKEND') != 'postgres':
        raise RuntimeError('Cloud worker requires PostgreSQL backend')
    if os.getenv('TELEGRAM_ENABLED', '').strip().lower() in {'1','true','yes','on'}:
        raise RuntimeError('Cloud worker prohibits Telegram in F3')
    key = 'manual:' + manual_request_id if manual_request_id else cycle_key(now or datetime.now(timezone.utc))
    started = time.monotonic()
    with _connect() as lock_conn:
        acquired = lock_conn.execute('SELECT pg_try_advisory_lock(%s) AS locked', (LOCK_KEY,)).fetchone()['locked']
        if not acquired:
            return 'BUSY'
        try:
            # Mark this time slot atomically. A previously OK slot never executes twice.
            with _connect() as conn:
                row = conn.execute('''INSERT INTO worker_cycles(cycle_key,status,attempt)
                       VALUES(%s,'RUNNING',1)
                       ON CONFLICT(cycle_key) DO UPDATE SET
                           status='RUNNING',started_at=now(),completed_at=NULL,
                           attempt=worker_cycles.attempt+1,error_code=NULL,duration_ms=NULL
                       WHERE worker_cycles.status <> 'OK'
                       RETURNING attempt''', (key,)).fetchone()
            if row is None:
                return 'SKIPPED'
            _heartbeat(key=key,status='OK',details='running')
            try:
                result = run_engine()
                # TradingAutomationEngine swallows exceptions, returning None and
                # persisting a success boolean: caller should wrap it appropriately.
                if result is False:
                    raise RuntimeError('EngineCycleFailure')
            except BaseException as exc:
                error = _safe_error(exc)
                elapsed = int((time.monotonic() - started)*1000)
                with _connect() as conn:
                    conn.execute('''UPDATE worker_cycles SET status='ERROR',error_code=%s,
                                    duration_ms=%s,completed_at=now() WHERE cycle_key=%s''',
                                 (error, elapsed, key))
                _heartbeat(key=key,status='ERROR',details=error)
                _telemetry(severity='ERROR',code='CYCLE_FAILED',key=key,message=error)
                return 'ERROR'
            elapsed = int((time.monotonic() - started)*1000)
            with _connect() as conn:
                conn.execute('''UPDATE worker_cycles SET status='OK',error_code=NULL,
                                duration_ms=%s,completed_at=now() WHERE cycle_key=%s''',
                             (elapsed,key))
            # Publish already-committed trade events; trading success is independent
            # of notification delivery and no algorithm method is modified.
            if os.getenv('PUSH_REAL_EVENTS_ENABLED') == 'true':
                try:
                    from app.notifications.persistent_outbox import enqueue_real_trade_events,enqueue_real_trade_signals
                    enqueue_real_trade_signals()
                    enqueue_real_trade_events()
                except Exception as exc:
                    _LOG.warning('F5 trade outbox failure: %s', type(exc).__name__)
            # F5 shadow-only audit: after committed OK, never enters trading decision path.
            if os.getenv('PUSH_SHADOW_EVENTS_ENABLED','false').lower() == 'true':
                try:
                    from app.notifications.persistent_outbox import record_shadow_cycle, mirror_recent_trade_events
                    record_shadow_cycle(key)
                    mirror_recent_trade_events()
                except Exception as exc:
                    # Record only exception type and PostgreSQL SQLSTATE, never SQL, URLs or credentials.
                    _LOG.warning('F5 shadow outbox failed: %s / SQLSTATE %s; trading unaffected',
                                 type(exc).__name__, getattr(exc, 'sqlstate', None) or 'N/A')
            _heartbeat(key=key,status='OK',success=True,details='completed')
            _telemetry(severity='INFO',code='CYCLE_COMPLETED',key=key,message='OK')
            return 'OK'
        finally:
            # pg_advisory_unlock is session-scoped, not transaction-scoped.
            lock_conn.execute('SELECT pg_advisory_unlock(%s) AS unlocked', (LOCK_KEY,))


def _build_engine():
    """Build the same V4 algorithm using a separate worker, not API lifespan."""
    from app.config import settings
    from app.main import (settings_service, trade_repository, automation_engine,
                          setup_context_manager, recover_downtime_opportunity)
    settings.validate_runtime()
    # Schema 0001 and 0002 are installed by the migration owner, never the
    # limited runtime worker. No external API calls until the cycle lock is held.
    with _connect() as conn:
        versions = {row['version'] for row in conn.execute(
            'SELECT version FROM schema_migrations').fetchall()}
    if not {'0001_initial', '0002_worker'} <= versions:
        raise RuntimeError('Database migrations 0001 and 0002 are required')
    # V5 cloud has no weekly recap. Preserve immutable V4 algorithm source:
    # disable only its legacy recap hook on the isolated V5 worker instance.
    automation_engine.ensure_pending_pnl_recap = lambda *args, **kwargs: None
    recovered = [False]
    def run_cycle():
        if not recovered[0]:
            recover_downtime_opportunity(trade_repository, setup_context_manager, settings)
            recovered[0] = True
        automation_engine.run_market_cycle()
        return trade_repository.get_runtime_bool('runtime.last_cycle_success') is True
    return run_cycle


def run_requested_cycle(run_engine: Callable[[], object]) -> str | None:
    """Consume at most one durable request, with the same advisory lock and engine."""
    with _connect() as conn:
        pending = conn.execute("""SELECT id FROM manual_cycle_requests
                                   WHERE status='PENDING'
                                   ORDER BY requested_at LIMIT 1""").fetchone()
    if pending is None:
        return None
    request_id = str(pending['id'])
    with _connect() as conn:
        previous = conn.execute('SELECT max(id) AS id FROM engine_snapshots').fetchone()
        prior_snapshot_id = int(previous['id'] or 0)

    # Claim is serialized even across worker instances by the unique PENDING index
    # and a row transition; run_once has the session advisory lock as second gate.
    with _connect() as conn:
        claimed = conn.execute("""UPDATE manual_cycle_requests SET status='RUNNING', started_at=now()
                                  WHERE id=%s AND status='PENDING' RETURNING id""",
                               (request_id,)).fetchone()
    if claimed is None:
        return None
    status = run_once(run_engine, manual_request_id=request_id)
    if status == 'BUSY':
        with _connect() as conn:
            conn.execute("""UPDATE manual_cycle_requests SET status='PENDING',started_at=NULL
                            WHERE id=%s AND status='RUNNING'""", (request_id,))
        return 'BUSY'
    if status == 'SKIPPED':
        # A replayed successful request must not start a second Engine cycle.
        status = 'OK'
    with _connect() as conn:
        snapshot = conn.execute("""SELECT id,created_at FROM engine_snapshots
                                   ORDER BY id DESC LIMIT 1""").fetchone() if status == 'OK' else None
        if status == 'OK' and (snapshot is None or int(snapshot['id']) <= prior_snapshot_id):
            status = 'ERROR'
            snapshot = None
        conn.execute("""UPDATE manual_cycle_requests
                        SET status=%s,completed_at=now(),snapshot_id=%s,snapshot_at=%s
                        WHERE id=%s AND status='RUNNING'""",
                     (status, snapshot['id'] if snapshot else None,
                      snapshot['created_at'] if snapshot else None, request_id))
    return status


def recover_orphaned_requests() -> None:
    """On startup, mark interrupted requests as failed only if no Engine holds the lock."""
    with _connect() as lock_conn:
        acquired = lock_conn.execute('SELECT pg_try_advisory_lock(%s) AS locked', (LOCK_KEY,)).fetchone()['locked']
        if not acquired:
            return
        try:
            with _connect() as conn:
                conn.execute("""UPDATE manual_cycle_requests SET status='ERROR',completed_at=now()
                                WHERE status='RUNNING'""")
        finally:
            lock_conn.execute('SELECT pg_advisory_unlock(%s) AS unlocked', (LOCK_KEY,))


def main() -> None:
    if os.environ.get('BTC_PROCESS_ROLE') != 'worker':
        raise RuntimeError('BTC_PROCESS_ROLE=worker required')
    if os.getenv('BTC_DB_BACKEND') != 'postgres':
        raise RuntimeError('Worker requires BTC_DB_BACKEND=postgres')
    if os.getenv('BTC_LIVE_TRADING', '').lower() not in ('','0','false','off','no'):
        raise RuntimeError('Live orders are forbidden during F3')
    from app.release_guard import enforce_cloud_isolation
    enforce_cloud_isolation(role='worker')
    cycle = _build_engine()
    recover_orphaned_requests()
    stop = False
    def on_shutdown(signum, frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, on_shutdown)
    signal.signal(signal.SIGINT, on_shutdown)
    _telemetry(severity='INFO',code='WORKER_STARTED',message='Scheduler initialized')
    while not stop:
        now=datetime.now(timezone.utc)
        if run_once(cycle,now=now)=='ERROR':
            _LOG.warning('Market cycle failed; next slot/retry will handle recovery')
        # The manual request uses the same cycle code and DB-wide lock.
        run_requested_cycle(cycle)
        # At most one slot every five minutes; don't hammer DB on crashes.
        sleep_time=max(1,min(10,INTERVAL_SECONDS-int(time.time())%INTERVAL_SECONDS))
        time.sleep(sleep_time)


if __name__ == '__main__':
    main()