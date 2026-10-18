"""F5 real trade Web Push transport (Preview): per-device dedup and bounded retries.

At-least-once transport: exactly-once external push cannot be guaranteed across
a process crash after provider acceptance and before the database commit.
The durable event and delivery primary keys prevent ordinary duplicate sends.
"""
from __future__ import annotations
import json, logging, os
from app.storage.postgres import connect_pg
from app.notifications.push_api import _cipher, _validate_endpoint
LOG=logging.getLogger("btc_v5.trade_push")
MAX_ATTEMPTS=5

def _send(subscription, payload):
    cipher=_cipher()
    endpoint=cipher.decrypt(bytes(subscription["endpoint_ciphertext"])).decode()
    _validate_endpoint(endpoint)
    data={"endpoint":endpoint,"keys":{
        "p256dh":cipher.decrypt(bytes(subscription["p256dh_ciphertext"])).decode(),
        "auth":cipher.decrypt(bytes(subscription["auth_ciphertext"])).decode()}}
    from pywebpush import webpush
    return webpush(subscription_info=data,data=json.dumps(payload),
        vapid_private_key=os.environ["PUSH_VAPID_PRIVATE_KEY"],
        vapid_claims={"sub":os.environ["PUSH_VAPID_SUBJECT"]},ttl=300,timeout=10)

def drain_real_events(limit=10):
    if os.getenv("PUSH_REAL_EVENTS_ENABLED")!="true" or os.getenv("PUSH_DISPATCHER_REAL_SEND")!="true":
        return {"state":"DISABLED","processed":0}
    if os.getenv("BTC_PROCESS_ROLE")!="push_dispatcher":
        raise RuntimeError("Push dispatcher role required")
    if not 1<=limit<=100: raise ValueError("limit")
    count=0
    with connect_pg() as db:
        events=db.execute("""SELECT id,public_payload,attempts,expires_at
            FROM v5_push_outbox WHERE kind='TRADE_EVENT' AND status='PENDING'
            AND next_attempt_at<=now() ORDER BY id
            LIMIT %s FOR UPDATE SKIP LOCKED""",(limit,)).fetchall()
        for event in events:
            if db.execute("SELECT now()>=%s AS expired",(event["expires_at"],)).fetchone()["expired"]:
                db.execute("UPDATE v5_push_outbox SET status='EXPIRED',updated_at=now() WHERE id=%s",(event["id"],))
                continue
            subscriptions=db.execute("""SELECT id,endpoint_ciphertext,p256dh_ciphertext,auth_ciphertext
                FROM v5_push_subscriptions WHERE active=true""").fetchall()
            for sub in subscriptions:
                db.execute("""INSERT INTO v5_push_deliveries(event_id,subscription_id)
                    VALUES (%s,%s) ON CONFLICT DO NOTHING""",(event["id"],sub["id"]))
            # Pending deliveries are retryable; SENT/EXPIRED are terminal.
            pending=db.execute("""SELECT d.subscription_id,d.attempts,s.endpoint_ciphertext,
                 s.p256dh_ciphertext,s.auth_ciphertext
                 FROM v5_push_deliveries d
                 JOIN v5_push_subscriptions s ON s.id=d.subscription_id
                 WHERE d.event_id=%s AND d.state='PENDING' AND s.active=true
                 ORDER BY d.subscription_id FOR UPDATE OF d""",(event["id"],)).fetchall()
            transient=False
            for sub in pending:
                next_attempt=int(sub["attempts"])+1
                state="PENDING";code=None
                try:
                    _send(sub,dict(event["public_payload"]))
                    state="SENT"
                except Exception as exc:
                    response=getattr(exc,"response",None)
                    http_code=getattr(response,"status_code",None)
                    if http_code in (404,410):
                        state="EXPIRED";code="SUBSCRIPTION_GONE"
                        db.execute("UPDATE v5_push_subscriptions SET active=false,updated_at=now() WHERE id=%s",(sub["subscription_id"],))
                    elif next_attempt>=MAX_ATTEMPTS:
                        state="FAILED";code="RETRY_EXHAUSTED"
                    else:
                        transient=True;code="PUSH_TRANSIENT"
                    LOG.warning("Trade Push transport %s (attempt %s)",code or "FAILED",next_attempt)
                db.execute("""UPDATE v5_push_deliveries SET state=%s,attempts=%s,
                    last_error_code=%s,delivered_at=CASE WHEN %s='SENT' THEN now() ELSE delivered_at END
                    WHERE event_id=%s AND subscription_id=%s""",
                    (state,next_attempt,code,state,event["id"],sub["subscription_id"]))
            remain=db.execute("""SELECT count(*) AS n FROM v5_push_deliveries
                   WHERE event_id=%s AND state='PENDING'""",(event["id"],)).fetchone()["n"]
            if remain:
                # Persist backoff per event, per delivery counters. Cap at 10 minutes.
                backoff=min(600,30*(2**min(int(event["attempts"]),5)))
                db.execute("""UPDATE v5_push_outbox SET attempts=attempts+1,
                    next_attempt_at=now()+(%s * interval '1 second'),updated_at=now()
                    WHERE id=%s""",(backoff,event["id"]))
            else:
                failed=db.execute("""SELECT count(*) AS n FROM v5_push_deliveries
                    WHERE event_id=%s AND state='FAILED'""",(event["id"],)).fetchone()["n"]
                status="FAILED" if failed else "SENT"
                db.execute("UPDATE v5_push_outbox SET status=%s,updated_at=now() WHERE id=%s",(status,event["id"]))
            count+=1
    return {"state":"RUNNING","processed":count}
