"""Temporary F5 user-triggered delayed test push only. No trading events."""
import os, json, logging
from datetime import datetime, timezone
from app.storage.postgres import connect_pg
from app.notifications.push_api import _cipher, _validate_endpoint
LOG=logging.getLogger(__name__)

def schedule(user_id:int, endpoint_hash:str)->dict:
    if os.getenv("PUSH_DELAYED_TEST_ENABLED")!="true":
        raise ValueError("Delayed test is disabled")
    with connect_pg() as db:
        subscription=db.execute("SELECT 1 FROM v5_push_subscriptions WHERE user_id=%s AND endpoint_hash=%s AND active=true",(user_id,endpoint_hash)).fetchone()
        if not subscription: raise LookupError("Active device not found")
        # Atomic rate limit: one pending test per device, minimum 180 sec between bookings.
        pending=db.execute("""SELECT id FROM v5_push_delayed_tests
               WHERE user_id=%s AND endpoint_hash=%s AND
               (status='PENDING' OR created_at>now()-interval '180 seconds')
               LIMIT 1""",(user_id,endpoint_hash)).fetchone()
        if pending: raise RuntimeError("A recent test already exists")
        row=db.execute("""INSERT INTO v5_push_delayed_tests(user_id,endpoint_hash,due_at)
               VALUES (%s,%s,now()+interval '120 seconds')
               RETURNING id,due_at""",(user_id,endpoint_hash)).fetchone()
    return {"scheduled":True,"id":str(row["id"]),"due_at":row["due_at"].isoformat()}

def _send(row, db):
    subscription=db.execute("""SELECT endpoint_ciphertext,p256dh_ciphertext,auth_ciphertext
        FROM v5_push_subscriptions WHERE user_id=%s AND endpoint_hash=%s AND active=true""",
        (row["user_id"],row["endpoint_hash"])).fetchone()
    if subscription is None: return "REVOKED"
    cipher=_cipher()
    endpoint=cipher.decrypt(bytes(subscription["endpoint_ciphertext"])).decode()
    _validate_endpoint(endpoint)
    details={"endpoint":endpoint,"keys":{
        "p256dh":cipher.decrypt(bytes(subscription["p256dh_ciphertext"])).decode(),
        "auth":cipher.decrypt(bytes(subscription["auth_ciphertext"])).decode()}}
    from pywebpush import webpush
    webpush(subscription_info=details,
       data=json.dumps({"kind":"BTC_V5_TEST","title":"BTC Swing V5"}),
       vapid_private_key=os.environ["PUSH_VAPID_PRIVATE_KEY"],
       vapid_claims={"sub":os.environ["PUSH_VAPID_SUBJECT"]},
       ttl=120,timeout=10)
    return "SENT"

def drain_delayed_tests(limit:int=10)->int:
    if os.getenv("PUSH_DELAYED_TEST_ENABLED")!="true": return 0
    if os.getenv("BTC_PROCESS_ROLE")!="push_dispatcher": raise RuntimeError("Wrong role")
    if not (os.getenv("PUSH_VAPID_PRIVATE_KEY") and os.getenv("PUSH_VAPID_SUBJECT")):
        raise RuntimeError("VAPID secrets missing")
    count=0
    # Transactional row lock prevents parallel dispatchers sending same test.
    with connect_pg() as db:
        rows=db.execute("""SELECT id,user_id,endpoint_hash FROM v5_push_delayed_tests
          WHERE status='PENDING' AND due_at<=now()
          ORDER BY due_at LIMIT %s FOR UPDATE SKIP LOCKED""",(limit,)).fetchall()
        for row in rows:
            try:
                state=_send(row,db)
            except Exception as exc:
                state="FAILED"
                LOG.warning("Delayed push failed: %s",type(exc).__name__)
            db.execute("UPDATE v5_push_delayed_tests SET status=%s,processed_at=now() WHERE id=%s",(state,row["id"]))
            count+=1
    return count
