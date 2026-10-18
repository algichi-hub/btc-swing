"""V5 cloud removes weekly recap controls without touching V4 golden engine."""
from unittest.mock import patch
from pydantic import ValidationError
import pytest
from app.main import automation_status, update_app_settings, SettingsUpdatePayload

def test_cloud_status_reads_worker_heartbeat(monkeypatch):
    monkeypatch.setenv("BTC_PROCESS_ROLE", "api")
    monkeypatch.setenv("BTC_DB_BACKEND", "postgres")
    info={"status":"OK","age_seconds":14,"last_success_at":"2026-10-18T12:35:17+00:00"}
    with patch("app.automation.cloud_worker.get_worker_health",return_value=info):
        result=automation_status()
    assert result["running"] is True
    assert result["interval_seconds"]==300
    assert result["last_market_cycle_at"]==info["last_success_at"]
    assert result["next_market_cycle_at"] is not None
    assert "pnl_recap_time" not in result
    assert "pnl_recap_weekday" not in result

def test_cloud_status_stale_heartbeat(monkeypatch):
    monkeypatch.setenv("BTC_PROCESS_ROLE","api")
    monkeypatch.setenv("BTC_DB_BACKEND","postgres")
    with patch("app.automation.cloud_worker.get_worker_health",return_value={"status":"OK","age_seconds":700,"last_success_at":"2026-10-18T12:00:00+00:00"}):
        result=automation_status()
    assert not result["running"] and result["is_stale"]

def test_settings_recap_fields_rejected_by_api():
    fields=SettingsUpdatePayload.model_fields
    assert "pnl_recap_time" not in fields
    assert "pnl_recap_weekday" not in fields
    with pytest.raises(ValidationError):
        SettingsUpdatePayload(pnl_recap_weekday="SUNDAY", pnl_recap_time="08:00")

def test_regular_cloud_settings_save_without_legacy_scheduler(monkeypatch):
    monkeypatch.setenv("BTC_PROCESS_ROLE","api")
    with patch("app.main.settings_service.update_many",return_value={"pnl_chart_days":30}) as save,patch("app.main.automation_scheduler.reschedule_pnl_recap") as reschedule:
        result=update_app_settings(SettingsUpdatePayload(pnl_chart_days=30))
    assert result=={"pnl_chart_days":30}
    save.assert_called_once()
    reschedule.assert_not_called()

def test_no_recap_ui_or_scheduler_in_cloud():
    from pathlib import Path
    assert 'pnl-recap-' not in Path("app/static/index.html").read_text()
    assert 'pnlRecap' not in Path("app/static/app.js").read_text()
    source=Path("app/automation/cloud_worker.py").read_text()
    assert "automation_engine.ensure_pending_pnl_recap = lambda" in source
