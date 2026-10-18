import pytest
from app.release_guard import enforce_cloud_isolation,assert_release_eligible

def test_cloud_disallows_telegram_credentials(monkeypatch):
    monkeypatch.setenv("BTC_DB_BACKEND","postgres")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN","test-not-secret")
    with pytest.raises(RuntimeError,match="Telegram secrets"):
        enforce_cloud_isolation(role="worker")

def test_cloud_disallows_live_trading(monkeypatch):
    monkeypatch.setenv("BTC_DB_BACKEND","postgres")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN",raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID",raising=False)
    monkeypatch.setenv("BTC_LIVE_TRADING","true")
    with pytest.raises(RuntimeError,match="real-money"):
        enforce_cloud_isolation(role="worker")

def test_dispatcher_requires_explicit_flags(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID","PUSH_DELAYED_TEST_ENABLED"):
        monkeypatch.delenv(k,raising=False)
    monkeypatch.setenv("BTC_LIVE_TRADING","false")
    monkeypatch.setenv("BTC_DB_BACKEND","postgres")
    monkeypatch.setenv("PUSH_DISPATCHER_REAL_SEND","true")
    monkeypatch.setenv("PUSH_REAL_EVENTS_ENABLED","false")
    with pytest.raises(RuntimeError,match="explicit events"):
        enforce_cloud_isolation(role="push_dispatcher")

def test_release_no_go_when_evidence_missing():
    with pytest.raises(RuntimeError,match="NO-GO"):
        assert_release_eligible({})
