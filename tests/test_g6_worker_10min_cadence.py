from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.automation.cloud_worker import INTERVAL_SECONDS, cycle_key


def test_ten_minute_slots_utc():
    assert INTERVAL_SECONDS == 600
    base = datetime(2026, 10, 25, 7, 0, tzinfo=timezone.utc)
    assert cycle_key(base) == cycle_key(base + timedelta(minutes=9, seconds=59))
    assert cycle_key(base) != cycle_key(base + timedelta(minutes=10))
    assert cycle_key(base + timedelta(minutes=10)) == (base + timedelta(minutes=10)).isoformat()


def test_automatic_guard_and_manual_trigger_remain_separate():
    s = Path("app/automation/cloud_worker.py").read_text(encoding="utf-8")
    loop = s.split("last_scheduled_slot = None", 1)[1]
    assert "if slot != last_scheduled_slot:" in loop
    assert "run_once(cycle, now=now)" in loop
    assert "run_requested_cycle(cycle)" in loop
    assert "time.sleep(2)" in loop
    assert "manual_request_id=request_id" in s
    assert "automation_engine.run_market_cycle()" in s
