from pathlib import Path


def test_manual_worker_uses_existing_official_lock_and_cycle():
    src = Path("app/automation/cloud_worker.py").read_text(encoding="utf-8")
    assert "manual_request_id: str | None = None" in src
    assert "key = 'manual:' + manual_request_id if manual_request_id else cycle_key" in src
    assert "SELECT pg_try_advisory_lock(%s) AS locked" in src
    assert "status = run_once(run_engine, manual_request_id=request_id)" in src
    assert "UPDATE manual_cycle_requests" in src
    assert "SELECT id,created_at FROM engine_snapshots" in src
    assert "int(snapshot['id']) <= prior_snapshot_id" in src
    assert "run_requested_cycle(cycle)" in src
    assert "recover_orphaned_requests()" in src


def test_worker_never_places_real_orders():
    src = Path("app/automation/cloud_worker.py").read_text(encoding="utf-8")
    assert "Live orders are forbidden during F3" in src
    assert "automation_engine.run_market_cycle()" in src
    assert "return trade_repository.get_runtime_bool('runtime.last_cycle_success') is True" in src
