"""F5 dispatcher: isolation-first, dry-run by default.
Claims due outbox events with SKIP LOCKED, never sends shadow engine events.
"""
from __future__ import annotations
import os,time,logging
from app.storage.postgres import connect_pg
from app.notifications.push_api import _cipher,_validate_endpoint
LOG=logging.getLogger("btc_v5.push")

def drain_once(limit:int=20) -> dict:
    if not 1<=limit<=100: raise ValueError("limit")
    if os.getenv("PUSH_DISPATCHER_ENABLED","false").lower()!="true":
        return {"state":"DISABLED","processed":0}
    real=os.getenv("PUSH_DISPATCHER_REAL_SEND","false").lower()=="true"
    # Never allow delivery of non-synthetic kind from this process.
    with connect_pg() as db:
        rows=db.execute("""SELECT id,kind,public_payload,expires_at FROM v5_push_outbox
          WHERE status='PENDING' AND next_attempt_at<=now()
          AND (claimed_until IS NULL OR claimed_until<now())
          AND kind='BTC_V5_TEST'
          ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""",(limit,)).fetchall()
        count=0
        for row in rows:
            if not real:
                # Dry-run does not consume pending items or expose recipients.
                count+=1
                continue
            # Synthetic events remain non-deliverable via the operational channel.
            # Only TRADE_EVENT is processed by trade_dispatcher.
            count+=1
            continue
    return {"state":"DRY_RUN","processed":count}

def main():
    if os.getenv("BTC_PROCESS_ROLE")!="push_dispatcher":
        raise RuntimeError("dispatcher role required")
    if os.getenv("BTC_DB_BACKEND")!="postgres":
        raise RuntimeError("Postgres required")
    if os.getenv("PUSH_DISPATCHER_REAL_SEND","false").lower()=="true" and os.getenv("PUSH_REAL_EVENTS_ENABLED")!="true":
        raise RuntimeError("Real dispatcher requires explicit event gate")
    from app.release_guard import enforce_cloud_isolation
    enforce_cloud_isolation(role='push_dispatcher')
    from app.notifications.trade_dispatcher import drain_real_events
    while True:
        try:
            drain_once()
            if os.getenv("PUSH_REAL_EVENTS_ENABLED")=="true":
                drain_real_events()
        except Exception:
            LOG.error("dispatcher cycle failed",exc_info=False)
        time.sleep(5)

if __name__=="__main__":main()
