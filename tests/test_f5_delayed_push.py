from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
import pytest
from app.notifications.push_api import schedule_delayed_push,PushTestRequest
from app.notifications.delayed_test import drain_delayed_tests

def test_disabled_by_default(monkeypatch):
    for name in ("PUSH_ENABLED","PUSH_TEST_ENABLED","PUSH_DELAYED_TEST_ENABLED"):
        monkeypatch.delenv(name,raising=False)
    with pytest.raises(HTTPException) as ex:
        schedule_delayed_push(PushTestRequest(id="a"*64),user=SimpleNamespace(id=1))
    assert ex.value.status_code==503
    assert drain_delayed_tests()==0

def test_delayed_requires_owned_device(monkeypatch):
    for key in ("PUSH_ENABLED","PUSH_TEST_ENABLED","PUSH_DELAYED_TEST_ENABLED"):
        monkeypatch.setenv(key,"true")
    with patch("app.notifications.delayed_test.schedule",side_effect=LookupError):
        with pytest.raises(HTTPException) as ex:
            schedule_delayed_push(PushTestRequest(id="a"*64),user=SimpleNamespace(id=1))
    assert ex.value.status_code==404

def test_delayed_rate_limit(monkeypatch):
    for key in ("PUSH_ENABLED","PUSH_TEST_ENABLED","PUSH_DELAYED_TEST_ENABLED"):
        monkeypatch.setenv(key,"true")
    with patch("app.notifications.delayed_test.schedule",side_effect=RuntimeError):
        with pytest.raises(HTTPException) as ex:
            schedule_delayed_push(PushTestRequest(id="a"*64),user=SimpleNamespace(id=1))
    assert ex.value.status_code==429

def test_delay_is_server_side_and_fixed():
    from pathlib import Path
    code=Path("app/notifications/delayed_test.py").read_text()
    assert "interval '30 seconds'" in code
    assert "FOR UPDATE SKIP LOCKED" in code
    assert "active=true" in code
    assert '"BTC_V5_TEST"' in code
    assert 'status=\'PENDING\'' in code
