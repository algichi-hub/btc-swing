"""F5 real transport remains opt-in, guarded and non-destructive."""
from types import SimpleNamespace
from fastapi import HTTPException
import pytest
from app.notifications.push_api import TestNotification, test_notification, Subscription, subscribe, push_config

def test_test_push_default_disabled(monkeypatch):
    monkeypatch.delenv("PUSH_ENABLED",raising=False)
    monkeypatch.delenv("PUSH_TEST_ENABLED",raising=False)
    with pytest.raises(HTTPException) as ex:
        test_notification(TestNotification(id="a"*64),user=SimpleNamespace(id=1))
    assert ex.value.status_code==503

def test_test_push_send_gate_without_permission(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED","true")
    monkeypatch.setenv("PUSH_TEST_ENABLED","false")
    with pytest.raises(HTTPException) as ex:
        test_notification(TestNotification(id="b"*64),user=SimpleNamespace(id=1))
    assert ex.value.status_code==503

def test_publish_key_not_exposed_when_disabled(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED","false")
    monkeypatch.setenv("PUSH_VAPID_PUBLIC_KEY","example-key")
    assert push_config(user=SimpleNamespace(id=1))=={"enabled":False,"public_key":""}

def test_reject_untrusted_provider_before_storage(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED","true")
    payload=Subscription(endpoint="https://malicious.invalid/example",keys={"p256dh":"a","auth":"b"})
    with pytest.raises(HTTPException) as ex:
        subscribe(payload,user=SimpleNamespace(id=1))
    assert ex.value.status_code==422
