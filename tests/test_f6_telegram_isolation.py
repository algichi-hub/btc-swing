"""F6-TG: no Telegram transport in cloud, V4 compatibility preserved."""
from pathlib import Path
import hashlib
import os

def test_frozen_algorithm_still_has_original_adapter_contract():
    code=Path("app/automation/trading_engine.py").read_bytes()
    assert b"telegram_notifier: TelegramNotifier" in code
    assert b"self.telegram_notifier = telegram_notifier" in code
    assert b"def run_market_cycle(" in code

def test_cloud_notifier_is_inert():
    from app.notifications.cloud_noop import NullLegacyNotifier,CloudNotificationDisabled
    n=NullLegacyNotifier()
    assert n.configured is False
    try:
        n.send_message("safety-probe")
    except CloudNotificationDisabled:
        pass
    else:
        raise AssertionError("Cloud notifier must never send")

def test_cloud_notifier_not_instantiated_from_real_telegram_transport():
    src=Path("app/main.py").read_text()
    assert "from app.notifications.telegram import TelegramNotifier" in src
    assert "from app.notifications.cloud_noop import NullLegacyNotifier" in src
    assert src.index("from app.notifications.cloud_noop import NullLegacyNotifier") < src.index("else:\n    # Compatibility")
    assert "def telegram_test(" not in src
    assert "def telegram_status(" not in src

def test_cloud_notifications_are_persisted_outbox_not_telegram_events():
    src=Path("app/notifications/persistent_outbox.py").read_text()
    assert "trade_signals" in src
    assert "trade_events" in src
    assert "v5_push_outbox" in src
    assert "telegram_events" not in src

def test_telegram_routes_absent_from_real_api(monkeypatch):
    monkeypatch.setenv("BTC_DB_BACKEND","postgres")
    monkeypatch.setenv("BTC_LIVE_TRADING","false")
    monkeypatch.setenv("TELEGRAM_ENABLED","false")
    monkeypatch.setenv("PUSH_DELAYED_TEST_ENABLED","false")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN",raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID",raising=False)
    from app.main import create_app
    app=create_app()
    source=Path("app/main.py").read_text()
    assert '@viewer_router.get("/telegram/status")' not in source
    assert '@admin_router.post("/telegram/test")' not in source
    assert "/telegram/status" not in {getattr(x,"path",None) for x in app.routes}
