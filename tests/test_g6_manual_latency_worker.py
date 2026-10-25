from pathlib import Path


def test_manual_poll_without_increasing_scheduled_cadence():
    source = Path("app/automation/cloud_worker.py").read_text()
    main = source.split("def main() -> None:", 1)[1]
    assert "last_scheduled_slot = None" in main
    assert "if slot != last_scheduled_slot:" in main
    assert "run_once(cycle, now=now)" in main
    assert "run_requested_cycle(cycle)" in main
    assert "time.sleep(2)" in main


def test_completion_bookkeeping_is_atomic_and_durable():
    source = Path("app/automation/cloud_worker.py").read_text()
    section = source.split("# One transaction/connection for completion bookkeeping", 1)[1].split("return 'OK'", 1)[0]
    assert "with _connect() as conn:" in section
    assert "INSERT INTO worker_heartbeat" in section
    assert "INSERT INTO operational_logs" in section
    assert "_heartbeat(key=key,status='OK'" not in section
    assert "_telemetry(severity='INFO',code='CYCLE_COMPLETED'" not in section


def test_official_engine_and_safety_guards_untouched():
    source = Path("app/automation/cloud_worker.py").read_text()
    assert "automation_engine.run_market_cycle()" in source
    assert "pg_try_advisory_lock" in source
    assert "Live orders are forbidden during F3" in source
    assert "int(snapshot['id']) <= prior_snapshot_id" in source
