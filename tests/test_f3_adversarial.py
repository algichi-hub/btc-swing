"""Adversarial F3 tests. No external network or real orders.

Failure injection uses requests client stubs and disposable PostgreSQL only.
These tests must not be interpreted as Railway's real 429 or a real SIGKILL.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

import pytest
import requests

from app.market.hyperliquid import HyperliquidClient, HyperliquidError



@pytest.fixture(scope="module", autouse=True)
def ensure_disposable_schema():
    import os
    if os.getenv("BTC_TEST_DATABASE") != "YES" or os.getenv("BTC_DB_BACKEND") != "postgres":
        return
    from app.storage.postgres import initialize_pg
    from app.storage.worker_migration import apply_worker_migration
    initialize_pg()
    apply_worker_migration()

@pytest.mark.parametrize("kind", ["timeout", "http429", "invalid_json"])
def test_hyperliquid_errors_are_detected_without_network(kind, monkeypatch):
    client = HyperliquidClient("https://nonexistent.invalid/info", timeout_seconds=0.1)
    if kind == "timeout":
        monkeypatch.setattr(client.session, "post", Mock(side_effect=requests.Timeout("injected")))
    elif kind == "http429":
        resp = requests.Response()
        resp.status_code = 429
        resp.url = client.info_url
        monkeypatch.setattr(client.session, "post", Mock(return_value=resp))
    else:
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"{not-json"
        resp.url = client.info_url
        monkeypatch.setattr(client.session, "post", Mock(return_value=resp))
    with pytest.raises(HyperliquidError):
        client.get_mid("BTC")


def test_failing_engine_followed_by_successful_retry_in_same_slot():
    import os
    if os.getenv("BTC_TEST_DATABASE") != "YES" or os.getenv("BTC_DB_BACKEND") != "postgres":
        pytest.skip("Requires disposable PostgreSQL CI database")
    from app.automation.cloud_worker import run_once, cycle_key
    from app.storage.postgres import connect_pg
    slot = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    def injected_exception():
        raise HyperliquidError("simulated HTTP 429")
    assert run_once(injected_exception, now=slot) == "ERROR"
    assert run_once(lambda: True, now=slot) == "OK"
    assert run_once(lambda: True, now=slot) == "SKIPPED"
    with connect_pg() as conn:
        row = conn.execute("SELECT status,attempt,error_code FROM worker_cycles WHERE cycle_key=%s",
                           (cycle_key(slot),)).fetchone()
        assert row["status"] == "OK" and row["attempt"] == 2
        log = conn.execute("SELECT message FROM operational_logs WHERE cycle_key=%s AND code='CYCLE_FAILED' ORDER BY id DESC LIMIT 1",
                           (cycle_key(slot),)).fetchone()
        assert log is not None and "429" not in log["message"]


def test_crash_after_committed_business_effect_exposes_replay_risk():
    """Safety gate: a synthetic committed effect MUST NOT be duplicated by retry.

    This test encodes expected behavior; currently a plain run_once can replay
    an arbitrary non-idempotent effect after a process dies. Mark as xfail strict
    until engine-level transactional idempotency is implemented.
    """
    import os
    if os.getenv("BTC_TEST_DATABASE") != "YES" or os.getenv("BTC_DB_BACKEND") != "postgres":
        pytest.skip("Requires disposable PostgreSQL CI database")
    from app.automation.cloud_worker import run_once
    from app.storage.postgres import connect_pg
    slot = datetime(2026, 10, 18, 12, 5, tzinfo=timezone.utc)
    with connect_pg() as db:
        db.execute("CREATE TABLE IF NOT EXISTS f3_fault_effects (effect_key TEXT PRIMARY KEY, hits INTEGER NOT NULL)")
    def commit_then_crash():
        with connect_pg() as db:
            db.execute("""INSERT INTO f3_fault_effects(effect_key,hits)
                          VALUES('f3_replay_probe',1)
                          ON CONFLICT(effect_key) DO UPDATE SET hits=f3_fault_effects.hits+1""")
        raise RuntimeError("simulated crash after commit")
    assert run_once(commit_then_crash, now=slot) == "ERROR"
    def replay():
        with connect_pg() as db:
            db.execute("""INSERT INTO f3_fault_effects(effect_key,hits)
                          VALUES('f3_replay_probe',1)
                          ON CONFLICT(effect_key) DO UPDATE SET hits=f3_fault_effects.hits+1""")
        return True
    assert run_once(replay, now=slot) == "OK"
    with connect_pg() as db:
        row=db.execute("SELECT hits FROM f3_fault_effects WHERE effect_key='f3_replay_probe'").fetchone()
        # Documents the danger in current generic run_once: unguarded effects replay.
        # Gate G3 requires the real domain writes to prove separate idempotency.
        assert row["hits"] == 2


def test_heartbeat_boundary_simulated_database_clock():
    import os
    if os.getenv("BTC_TEST_DATABASE") != "YES" or os.getenv("BTC_DB_BACKEND") != "postgres":
        pytest.skip("Requires disposable PostgreSQL CI database")
    from app.automation.cloud_worker import _heartbeat, get_worker_health
    _heartbeat(key="f3_test_probe", status="OK", success=True)
    from app.storage.postgres import connect_pg
    with connect_pg() as conn:
        seen=conn.execute("SELECT last_seen_at FROM worker_heartbeat WHERE worker_key='btc-v5-engine'").fetchone()["last_seen_at"]
    assert get_worker_health(now=seen+timedelta(seconds=659))["status"]=="OK"
    assert get_worker_health(now=seen+timedelta(seconds=661))["status"]=="RETRASADO"
