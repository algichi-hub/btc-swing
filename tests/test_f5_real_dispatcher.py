"""F5 real Push pipeline contract: fail closed, idempotent and no trading mutations."""
from pathlib import Path
from app.notifications.trade_dispatcher import drain_real_events
from app.notifications.persistent_outbox import enqueue_real_trade_events,enqueue_real_trade_signals

def test_real_delivery_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PUSH_REAL_EVENTS_ENABLED",raising=False)
    monkeypatch.delenv("PUSH_DISPATCHER_REAL_SEND",raising=False)
    assert drain_real_events()=={"state":"DISABLED","processed":0}
    assert enqueue_real_trade_events()==0
    assert enqueue_real_trade_signals()==0

def test_dispatcher_has_retry_and_subscription_cleanup():
    text=Path("app/notifications/trade_dispatcher.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in text
    assert "MAX_ATTEMPTS=5" in text
    assert "404,410" in text
    assert "PUSH_DISPATCHER_REAL_SEND" in text
    assert "PUSH_REAL_EVENTS_ENABLED" in text
    assert "last_error_code" in text

def test_sources_use_persisted_rows_no_algorithm_changes():
    text=Path("app/notifications/persistent_outbox.py").read_text()
    assert "FROM trade_signals" in text
    assert "FROM trade_events" in text
    assert text.count("ON CONFLICT(event_key) DO NOTHING")>=3
    assert "PUSH_REAL_EVENTS_SINCE" in text
    assert "'TRADE_EVENT'" in text

def test_service_worker_displays_allowlisted_trades():
    script=Path("app/static/sw.js").read_text()
    assert "payload.kind!=='TRADE_EVENT'" in script
    assert "Nueva señal de entrada" in script
    assert "Stop loss ejecutado" in script
    assert "BTC_V5_TEST" in script
    assert "Object.prototype.hasOwnProperty.call(messages,event)" in script
