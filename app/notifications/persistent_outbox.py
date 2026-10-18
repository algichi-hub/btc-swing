"""Transactional, idempotent PostgreSQL outbox for F5 Preview.

No secrets or trading payloads stored. A shadow event never sends a notification.
"""
from __future__ import annotations
import hashlib
from datetime import datetime,timezone
from app.storage.postgres import connect_pg

def record_shadow_cycle(cycle_key: str) -> bool:
    """Called after a committed OK worker slot; idempotent, non-operational."""
    if not cycle_key or len(cycle_key)>100:
        raise ValueError("invalid cycle key")
    key=hashlib.sha256(("shadow:v1:"+cycle_key).encode()).hexdigest()
    with connect_pg() as db:
        cursor=db.execute("""INSERT INTO v5_push_outbox
          (event_key,kind,public_payload,status,expires_at)
          VALUES (%s,'CYCLE_SHADOW','{}'::jsonb,'SENT',now()+interval '24 hours')
          ON CONFLICT(event_key) DO NOTHING""",(key,))
    return cursor.rowcount == 1

def enqueue_synthetic_test(event_key: str, ttl_minutes:int=10) -> bool:
    """Only opted-in synthetic test events, never engine decisions."""
    if not event_key or len(event_key)>100 or not 1<=ttl_minutes<=60:
        raise ValueError("invalid test")
    key=hashlib.sha256(("synthetic:v1:"+event_key).encode()).hexdigest()
    with connect_pg() as db:
        row=db.execute("""INSERT INTO v5_push_outbox
        (event_key,kind,public_payload,status,expires_at)
        VALUES (%s,'BTC_V5_TEST','{"kind":"BTC_V5_TEST","title":"BTC Swing V5"}'::jsonb,
                'PENDING',now()+(%s * interval '1 minute'))
        ON CONFLICT(event_key) DO NOTHING""",(key,ttl_minutes))
    return row is not None

def mirror_recent_trade_events(*, lookback_minutes: int = 15) -> int:
    """Shadow-read persisted trade events, never emit actual push or alter trading.

    Select event IDs only. The unique digest prevents duplicate shadow entries
    across retries, repeated cycles or multiple workers.
    """
    if not 1 <= lookback_minutes <= 60:
        raise ValueError("invalid lookback")
    with connect_pg() as db:
        rows=db.execute("""SELECT id FROM trade_events
            WHERE event_at::timestamptz >= now() - (%s * interval '1 minute')
            ORDER BY id LIMIT 100""",(lookback_minutes,)).fetchall()
        inserted=0
        for row in rows:
            key=hashlib.sha256(("trade-event-shadow:v1:"+str(row["id"])).encode()).hexdigest()
            created=db.execute("""INSERT INTO v5_push_outbox
                 (event_key,kind,public_payload,status,expires_at)
                 VALUES (%s,'TRADE_EVENT_SHADOW','{}'::jsonb,'SENT',
                   now()+interval '24 hours')
                 ON CONFLICT(event_key) DO NOTHING""",(key,))
            inserted+=int(created.rowcount == 1)
    return inserted

def enqueue_real_trade_events(*, lookback_days: int = 7) -> int:
    """Mirror only committed trade_events. Does not invoke or change the algorithm.

    Deduplicates by the immutable database event ID, including worker retries.
    Historic events are ignored beyond seven days; the dispatcher expires stale
    messages after 24 hours. Notification contains no prices, PnL or wallet data.
    """
    if not 1 <= lookback_days <= 7:
        raise ValueError("invalid lookback")
    if __import__("os").getenv("PUSH_REAL_EVENTS_ENABLED") != "true":
        return 0
    since=__import__("os").getenv("PUSH_REAL_EVENTS_SINCE")
    if not since: return 0
    with connect_pg() as db:
        rows=db.execute("""SELECT id,event_type FROM trade_events
            WHERE event_at::timestamptz >= %s::timestamptz
            ORDER BY id LIMIT 10000""",(since,)).fetchall()
        added=0
        for row in rows:
            kind=str(row["event_type"]).upper()
            if kind not in {"OPEN","ENTRY","OPENED","TP1","TP2","TP3","SL","CLOSE","CLOSED","TAKE_PROFIT","STOP_LOSS"}:
                continue
            key=hashlib.sha256(("trade-event:v1:"+str(row["id"])).encode()).hexdigest()
            c=db.execute("""INSERT INTO v5_push_outbox(event_key,kind,public_payload,status,expires_at)
                VALUES(%s,'TRADE_EVENT',%s::jsonb,'PENDING',now()+interval '24 hours')
                ON CONFLICT(event_key) DO NOTHING""",(key,__import__("json").dumps({"kind":"TRADE_EVENT","event":kind,"title":"BTC Swing V5","id":key[:16]})))
            added+=int(c.rowcount==1)
    return added

def enqueue_real_trade_signals() -> int:
    """Announce new paper trade entries once; never place or alter an order."""
    import os,json
    since=os.getenv("PUSH_REAL_EVENTS_SINCE")
    if os.getenv("PUSH_REAL_EVENTS_ENABLED")!="true" or not since: return 0
    with connect_pg() as db:
        rows=db.execute("""SELECT id FROM trade_signals
            WHERE created_at::timestamptz >= %s::timestamptz
            AND status='OPEN' ORDER BY id LIMIT 10000""",(since,)).fetchall()
        added=0
        for row in rows:
            key=hashlib.sha256(("trade-signal:v1:"+str(row["id"])).encode()).hexdigest()
            result=db.execute("""INSERT INTO v5_push_outbox
                (event_key,kind,public_payload,status,expires_at)
                VALUES (%s,'TRADE_EVENT',%s::jsonb,'PENDING',now()+interval '24 hours')
                ON CONFLICT(event_key) DO NOTHING""",(key,json.dumps({
                    "kind":"TRADE_EVENT","event":"OPEN","title":"BTC Swing V5","id":key[:16]})))
            added+=int(result.rowcount==1)
    return added
