"""F5 authenticated Web Push subscription API.
Disabled unless PUSH_ENABLED=true and secrets configured. Not a trading signal source.
"""
from __future__ import annotations
import hashlib
import json
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.auth.http import get_current_user, verify_csrf_origin, verify_csrf_token
from app.storage.postgres import connect_pg

router = APIRouter(prefix="/api/push", tags=["push"])
ALLOW_HOSTS = (".push.services.mozilla.com", ".fcm.googleapis.com", ".googleapis.com", ".notify.windows.com", ".push.apple.com")

def _enabled():
    return os.getenv("PUSH_ENABLED", "false").lower() == "true"

def _cipher():
    from cryptography.fernet import Fernet
    key = os.getenv("PUSH_SUBSCRIPTION_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("Push subscription encryption secret missing")
    return Fernet(key.encode())

def _validate_endpoint(endpoint: str):
    u = urlparse(endpoint)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None,443):
        raise HTTPException(status_code=422, detail="Invalid push endpoint")
    if not any(u.hostname == h.lstrip(".") or u.hostname.endswith(h) for h in ALLOW_HOSTS):
        raise HTTPException(status_code=422, detail="Push provider not allowed")

class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    endpoint: str = Field(max_length=2048)
    keys: dict[str, str]
    device_label: str = Field(default="Device", max_length=100)

@router.get("/config")
def push_config(user=Depends(get_current_user)):
    return {"enabled":_enabled(), "public_key":os.getenv("PUSH_VAPID_PUBLIC_KEY","") if _enabled() else ""}

@router.get("/devices")
def devices(user=Depends(get_current_user)):
    if not _enabled():
        return {"items":[],"enabled":False}
    with connect_pg() as c:
        rows=c.execute("SELECT endpoint_hash, device_label, created_at FROM v5_push_subscriptions WHERE user_id=%s AND active=true ORDER BY created_at DESC", (user.id,)).fetchall()
    return {"enabled":True,"items":[{"id":r["endpoint_hash"],"label":r["device_label"],"created_at":str(r["created_at"])} for r in rows]}

@router.post("/subscribe",dependencies=[Depends(verify_csrf_origin),Depends(verify_csrf_token)])
def subscribe(payload: Subscription,user=Depends(get_current_user)):
    if not _enabled():
        raise HTTPException(status_code=503,detail="Push disabled")
    _validate_endpoint(payload.endpoint)
    if set(payload.keys) != {"p256dh","auth"}:
        raise HTTPException(status_code=422,detail="Invalid subscription keys")
    import base64
    try:
        for k in ("p256dh","auth"):
            raw=base64.urlsafe_b64decode(payload.keys[k]+"===")
            if len(raw)!=(65 if k=="p256dh" else 16):
                raise ValueError()
    except Exception:
        raise HTTPException(status_code=422,detail="Invalid subscription key")
    cipher=_cipher()
    digest=hashlib.sha256(payload.endpoint.encode()).hexdigest()
    with connect_pg() as c:
        existing=c.execute("SELECT user_id FROM v5_push_subscriptions WHERE endpoint_hash=%s",(digest,)).fetchone()
        if existing and existing["user_id"] != user.id:
            raise HTTPException(status_code=409,detail="Subscription belongs to another account")
        c.execute("""INSERT INTO v5_push_subscriptions(user_id,endpoint_hash,endpoint_ciphertext,p256dh_ciphertext,auth_ciphertext,device_label)
        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(endpoint_hash) DO UPDATE SET
        active=true,device_label=EXCLUDED.device_label,updated_at=now()""",
        (user.id,digest,cipher.encrypt(payload.endpoint.encode()),cipher.encrypt(payload.keys["p256dh"].encode()),cipher.encrypt(payload.keys["auth"].encode()),payload.device_label))
    return {"id":digest, "active":True}

class RemoveDevice(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")

@router.post("/revoke",dependencies=[Depends(verify_csrf_origin),Depends(verify_csrf_token)])
def revoke(body:RemoveDevice,user=Depends(get_current_user)):
    if not _enabled():
        raise HTTPException(status_code=503,detail="Push disabled")
    with connect_pg() as c:
        c.execute("UPDATE v5_push_subscriptions SET active=false, updated_at=now() WHERE endpoint_hash=%s AND user_id=%s",(body.id,user.id))
    return {"ok":True}

class TestNotification(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")

@router.post("/test", dependencies=[Depends(verify_csrf_origin), Depends(verify_csrf_token)])
def test_notification(body:TestNotification,user=Depends(get_current_user)):
    """Send one non-sensitive notification to an opted-in device.
    No trading/event pipeline integration in this endpoint.
    """
    if not _enabled() or os.getenv("PUSH_TEST_ENABLED","false").lower() != "true":
        raise HTTPException(status_code=503,detail="Test sending disabled")
    private_key=os.getenv("PUSH_VAPID_PRIVATE_KEY","")
    subject=os.getenv("PUSH_VAPID_SUBJECT","")
    if not private_key or not (subject.startswith("mailto:") or subject.startswith("https://")):
        raise HTTPException(status_code=503, detail="Push service not configured")
    with connect_pg() as c:
        row=c.execute("""SELECT endpoint_ciphertext,p256dh_ciphertext,auth_ciphertext
        FROM v5_push_subscriptions WHERE endpoint_hash=%s AND user_id=%s AND active=true""",
        (body.id,user.id)).fetchone()
    if not row:
        raise HTTPException(status_code=404,detail="Device not found")
    with connect_pg() as c:
        permit=c.execute("""INSERT INTO v5_push_test_quota(user_id,endpoint_hash,last_sent_at)
        VALUES (%s,%s,now()) ON CONFLICT(user_id,endpoint_hash) DO UPDATE
        SET last_sent_at=now()
        WHERE v5_push_test_quota.last_sent_at < now() - INTERVAL '60 seconds'
        RETURNING endpoint_hash""",(user.id,body.id)).fetchone()
    if not permit:
        raise HTTPException(status_code=429,detail="Wait before testing this device again")
    cipher=_cipher()
    endpoint=cipher.decrypt(bytes(row["endpoint_ciphertext"])).decode()
    _validate_endpoint(endpoint)
    subscription={"endpoint":endpoint,"keys":{
       "p256dh":cipher.decrypt(bytes(row["p256dh_ciphertext"])).decode(),
       "auth":cipher.decrypt(bytes(row["auth_ciphertext"])).decode()}}
    try:
        from pywebpush import webpush, WebPushException
        webpush(subscription_info=subscription,
                data=json.dumps({"kind":"BTC_V5_TEST","title":"BTC Swing V5"}),
                vapid_private_key=private_key,
                vapid_claims={"sub":subject}, ttl=120, timeout=10)
    except Exception as exc:
        # Do not echo endpoint, user keys, URL or provider error to clients.
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Push provider unavailable") from None
    return {"accepted":True}
