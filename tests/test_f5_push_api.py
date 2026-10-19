"""F5 security contract for Web Push endpoints (no network / actual credentials)."""
import os
import pytest
from fastapi import HTTPException

from app.notifications.push_api import Subscription, _validate_endpoint, _enabled

@pytest.mark.parametrize("endpoint",[
 "http://fcm.googleapis.com/push","https://evil.example/abc",
 "https://localhost/api","https://127.0.0.1/x",
 "https://test.push.services.mozilla.com.evil.com/x",
 "https://user:pass@fcm.googleapis.com/push",
 "https://fcm.googleapis.com:444/push"])
def test_provider_ssrf_rejected(endpoint):
    with pytest.raises(HTTPException) as e:
        _validate_endpoint(endpoint)
    assert e.value.status_code==422

@pytest.mark.parametrize("endpoint",[
 "https://fcm.googleapis.com/fcm/send/X",
 "https://updates.push.services.mozilla.com/wpush/v2/X",
 "https://web.push.apple.com/Q"])
def test_official_push_hosts_allowed(endpoint):
    _validate_endpoint(endpoint)

def test_default_disabled(monkeypatch):
    monkeypatch.delenv("PUSH_ENABLED",raising=False)
    assert not _enabled()
    monkeypatch.setenv("PUSH_ENABLED","true")
    assert _enabled()
    monkeypatch.setenv("PUSH_ENABLED","false")
    assert not _enabled()

def test_subscription_rejects_incomplete_schema():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Subscription(endpoint="https://fcm.googleapis.com/push",keys={"p256dh":"x"},untrusted="oops")
