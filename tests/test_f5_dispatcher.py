"""F5 simulated dispatcher contract; no real provider access."""
from datetime import timedelta
import pytest
from app.notifications.push_dispatcher_dryrun import DryRunDispatcher

def test_device_idempotent_and_private_to_owner():
    d=DryRunDispatcher()
    a=d.subscribe_synthetic(1,"test://device-a")
    assert d.subscribe_synthetic(1,"test://device-a") is a
    with pytest.raises(PermissionError):
        d.subscribe_synthetic(2,"test://device-a")
    with pytest.raises(ValueError):
        d.subscribe_synthetic(1,"https://push.provider.real/secret")

def test_exactly_one_logical_delivery_per_device():
    d=DryRunDispatcher()
    d.subscribe_synthetic(1,"test://a")
    d.subscribe_synthetic(1,"test://b")
    d.subscribe_synthetic(2,"test://c")
    assert d.stage("event1",1)==2
    assert d.stage("event1",1)==0
    assert d.drain(lambda _:True)==2
    assert d.drain(lambda _:True)==0

def test_revoke_stops_pending_delivery():
    d=DryRunDispatcher()
    a=d.subscribe_synthetic(1,"test://a")
    assert d.stage("event1",1)==1
    assert not d.revoke(2,a.endpoint_hash)
    assert d.revoke(1,a.endpoint_hash)
    assert d.drain(lambda _:True)==0
    assert list(d.deliveries.values())[0].status=="REVOKED"

def test_retry_exponential_then_permanent_failure():
    d=DryRunDispatcher(max_attempts=3)
    d.subscribe_synthetic(1,"test://a")
    d.stage("event1",1)
    row=list(d.deliveries.values())[0]
    t=row.due_at
    assert d.drain(lambda _:False, t)==0 and row.attempts==1
    assert row.due_at==t+timedelta(seconds=60)
    assert d.drain(lambda _:False,t+timedelta(seconds=61))==0 and row.attempts==2
    assert d.drain(lambda _:False,t+timedelta(seconds=181))==0
    assert row.status=="FAILED" and row.attempts==3

def test_sender_exception_sanitized():
    d=DryRunDispatcher(max_attempts=1)
    d.subscribe_synthetic(1,"test://a")
    d.stage("event1",1)
    assert d.drain(lambda _: (_ for _ in ()).throw(RuntimeError("sensitive-url")))==0
    row=list(d.deliveries.values())[0]
    assert row.error_code=="MAX_RETRIES" and "sensitive-url" not in str(row)
