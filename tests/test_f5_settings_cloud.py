"""Regression of cloud status/scheduling boundary. Preview API has no local scheduler."""
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch
from app.main import automation_status, update_app_settings, SettingsUpdatePayload

def test_cloud_status_reads_worker_heartbeat(monkeypatch):
    monkeypatch.setenv("BTC_PROCESS_ROLE","api")
    monkeypatch.setenv("BTC_DB_BACKEND","postgres")
    info={"status":"OK","age_seconds":14,"last_success_at":"2026-10-18T12:35:17+00:00"}
    with patch("app.automation.cloud_worker.get_worker_health",return_value=info), patch("app.main.settings_service.get_all",return_value={"pnl_recap_weekday":"SUNDAY","pnl_recap_time":"08:00"}):
        result=automation_status()
    assert result["running"] is True
    assert result["interval_seconds"]==300
    assert result["last_market_cycle_at"]==info["last_success_at"]
    assert result["next_market_cycle_at"] is not None
    assert result["pnl_recap_time"]=="08:00"

def test_cloud_status_stale_heartbeat(monkeypatch):
    monkeypatch.setenv("BTC_PROCESS_ROLE","api")
    monkeypatch.setenv("BTC_DB_BACKEND","postgres")
    with patch("app.automation.cloud_worker.get_worker_health",return_value={"status":"OK","age_seconds":700,"last_success_at":"2026-10-18T12:00:00+00:00"}), patch("app.main.settings_service.get_all",return_value={"pnl_recap_weekday":"SUNDAY","pnl_recap_time":"08:00"}):
        result=automation_status()
    assert not result["running"] and result["is_stale"]

def test_cloud_recap_saves_without_local_scheduler(monkeypatch):
    monkeypatch.setenv("BTC_PROCESS_ROLE","api")
    with patch("app.main.settings_service.update_many",return_value={"pnl_recap_weekday":"SUNDAY","pnl_recap_time":"08:00"}) as save,patch("app.main.automation_scheduler.reschedule_pnl_recap") as reschedule:
        result=update_app_settings(SettingsUpdatePayload(pnl_recap_weekday="SUNDAY",pnl_recap_time="08:00"))
    assert result["pnl_recap_time"]=="08:00"
    save.assert_called_once()
    reschedule.assert_not_called()
