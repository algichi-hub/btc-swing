"""Real operating-system process kill in F3, using only disposable CI PostgreSQL.

No market HTTP, no live orders; validates advisory lock release on SIGKILL
and idempotent PAPER insert when the cycle is re-executed after a DB commit.
"""
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest


def test_sigkill_after_commit_then_resume_without_duplicate():
    if os.getenv("BTC_TEST_DATABASE") != "YES" or os.getenv("BTC_DB_BACKEND") != "postgres":
        pytest.skip("Requires dedicated disposable Postgres CI service")
    if sys.platform == "win32":
        pytest.skip("SIGKILL requires Unix")
    from app.storage.postgres import initialize_pg, connect_pg
    from app.storage.worker_migration import apply_worker_migration
    from app.storage.trade_repository import TradeRepository
    from app.automation.cloud_worker import run_once, cycle_key
    initialize_pg()
    apply_worker_migration()
    slot = datetime(2026, 10, 18, 13, 15, tzinfo=timezone.utc)
    fingerprint = "f3-sigkill-after-db-commit"
    plan = dict(entry=100.0, sl=95.0, tp1=105.0, tp2=110.0,
                tp3=115.0, rr1=1.0, rr2=2.0, rr3=3.0, weighted_rr=2.1,
                margin_usd=100.0, leverage=5, notional_usd=500.0)
    code = """
import os, signal
from datetime import datetime,timezone
from pathlib import Path
from app.automation.cloud_worker import run_once
from app.storage.trade_repository import TradeRepository
p=dict(entry=100.,sl=95.,tp1=105.,tp2=110.,tp3=115.,
       rr1=1.,rr2=2.,rr3=3.,weighted_rr=2.1,
       margin_usd=100.,leverage=5,notional_usd=500.)
r=TradeRepository(Path('unused-f3-kill.db'))
def write_and_die():
    r.create_paper_trade(fingerprint='f3-sigkill-after-db-commit',
       created_at='2026-10-18T13:15:00+00:00',side='LONG',
       state_at_entry='CONFIRMED',daily_swing_candles_at_signal=120,plan=p)
    os.kill(os.getpid(),signal.SIGKILL)
run_once(write_and_die,now=datetime(2026,10,18,13,15,tzinfo=timezone.utc))
"""
    killed = subprocess.run([sys.executable, "-c", code], timeout=20,
                            check=False, capture_output=True, text=True)
    assert killed.returncode == -signal.SIGKILL, killed.stderr[-1000:]
    with connect_pg() as conn:
        row = conn.execute(
            "SELECT status,attempt FROM worker_cycles WHERE cycle_key=%s",
            (cycle_key(slot),)).fetchone()
        count = conn.execute(
            "SELECT count(*) AS n FROM trade_signals WHERE fingerprint=%s",
            (fingerprint,)).fetchone()["n"]
        assert row["status"] == "RUNNING" and row["attempt"] == 1
        assert count == 1

    repo = TradeRepository(Path("unused-f3-kill.db"))
    def restart():
        signal_id = repo.create_paper_trade(
            fingerprint=fingerprint,
            created_at="2026-10-18T13:15:00+00:00", side="LONG",
            state_at_entry="CONFIRMED",daily_swing_candles_at_signal=120,plan=plan)
        assert signal_id > 0
        return True
    assert run_once(restart,now=slot) == "OK"
    assert run_once(restart,now=slot) == "SKIPPED"
    with connect_pg() as conn:
        row = conn.execute(
            "SELECT status,attempt FROM worker_cycles WHERE cycle_key=%s",
            (cycle_key(slot),)).fetchone()
        n = conn.execute(
            "SELECT count(*) AS n FROM trade_signals WHERE fingerprint=%s",
            (fingerprint,)).fetchone()["n"]
    assert row["status"] == "OK" and row["attempt"] == 2
    assert n == 1
