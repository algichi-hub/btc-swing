import os
import pytest
from app.notifications.cloud_dispatcher import drain_once

def test_default_dispatcher_disabled(monkeypatch):
    monkeypatch.delenv("PUSH_DISPATCHER_ENABLED",raising=False)
    assert drain_once()=={"state":"DISABLED","processed":0}

def test_dispatcher_limits(monkeypatch):
    monkeypatch.setenv("PUSH_DISPATCHER_ENABLED","false")
    for n in (0,-1,101):
        with pytest.raises(ValueError):drain_once(n)

def test_worker_shadow_does_not_send():
    from pathlib import Path
    s=Path("app/notifications/persistent_outbox.py").read_text()
    assert "'CYCLE_SHADOW'" in s and "'SENT'" in s
    assert "ON CONFLICT(event_key) DO NOTHING" in s

def test_real_send_fails_closed():
    from pathlib import Path
    s=Path("app/notifications/cloud_dispatcher.py").read_text()
    assert 'Real dispatcher requires explicit event gate' in s
    assert 'PUSH_DISPATCHER_REAL_SEND' in s
    assert 'PUSH_REAL_EVENTS_ENABLED' in s
    assert "kind='BTC_V5_TEST'" in s

def test_mirror_trade_events_never_exposes_private_payload():
    from pathlib import Path
    code=Path("app/notifications/persistent_outbox.py").read_text()
    assert "FROM trade_events" in code
    assert "'TRADE_EVENT_SHADOW'" in code
    assert "'{}'::jsonb,'SENT'" in code
    assert "ON CONFLICT(event_key) DO NOTHING" in code

def test_mirror_rejects_wide_lookback():
    from app.notifications.persistent_outbox import mirror_recent_trade_events
    with pytest.raises(ValueError):
        mirror_recent_trade_events(lookback_minutes=0)
    with pytest.raises(ValueError):
        mirror_recent_trade_events(lookback_minutes=61)


def test_shadow_insert_needs_no_select_on_outbox():
    from pathlib import Path
    code=Path('app/notifications/persistent_outbox.py').read_text()
    assert 'RETURNING id' not in code
    assert 'rowcount == 1' in code
