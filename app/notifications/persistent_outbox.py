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
        row=db.execute("""INSERT INTO v5_push_outbox
          (event_key,kind,public_payload,status,expires_at)
          VALUES (%s,'CYCLE_SHADOW','{}'::jsonb,'SENT',now()+interval '24 hours')
          ON CONFLICT(event_key) DO NOTHING RETURNING id""",(key,)).fetchone()
    return row is not None

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
        ON CONFLICT(event_key) DO NOTHING RETURNING id""",(key,ttl_minutes)).fetchone()
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
                 ON CONFLICT(event_key) DO NOTHING RETURNING id""",(key,)).fetchone()
            inserted+=int(created is not None)
    return inserted
