"""Crash replay checks for actual F3 paper-trading domain writes.

All writes are confined to a disposable PostgreSQL instance in CI.
"""
import os
from datetime import datetime,timezone
from pathlib import Path
import pytest

@pytest.fixture(scope="module", autouse=True)
def fresh_postgres():
    if os.getenv("BTC_TEST_DATABASE") != "YES" or os.getenv("BTC_DB_BACKEND") != "postgres":
        pytest.skip("Must run with disposable CI postgres")
    from app.storage.postgres import initialize_pg
    from app.storage.worker_migration import apply_worker_migration
    initialize_pg()
    apply_worker_migration()


def _plan():
    return dict(entry=100.0,sl=95.0,tp1=105.0,tp2=110.0,tp3=115.0,
                rr1=1.0,rr2=2.0,rr3=3.0,weighted_rr=2.1,
                margin_usd=100.0,leverage=5,notional_usd=500.0)


def test_v4_trade_insert_is_idempotent_after_crash_replay():
    from app.automation.cloud_worker import run_once
    from app.storage.trade_repository import TradeRepository
    from app.storage.postgres import connect_pg
    repo=TradeRepository(Path("not-used-postgres.db"))
    args=dict(fingerprint="f3-domain-replay",
              created_at="2026-10-18T13:00:00+00:00",side="LONG",
              state_at_entry="CONFIRMED",daily_swing_candles_at_signal=120,plan=_plan())
    slot=datetime(2026,10,18,13,0,tzinfo=timezone.utc)
    ids=[]
    def fail_after_persistent_insert():
        ids.append(repo.create_paper_trade(**args))
        raise RuntimeError("SimulatedCrashAfterBusinessWrite")
    assert run_once(fail_after_persistent_insert,now=slot)=="ERROR"
    def resume():
        ids.append(repo.create_paper_trade(**args))
        return True
    assert run_once(resume,now=slot)=="OK"
    assert ids[0]==ids[1]
    with connect_pg() as conn:
        record=conn.execute("SELECT count(*) AS n FROM trade_signals WHERE fingerprint=%s",
                            (args["fingerprint"],)).fetchone()
        assert record["n"]==1


def test_v4_exit_update_is_exactly_once_on_retry():
    from app.storage.trade_repository import TradeRepository
    from app.storage.postgres import connect_pg
    repo=TradeRepository(Path("not-used-postgres.db"))
    signal_id=repo.create_paper_trade(
        fingerprint="f3-domain-exit-once",
        created_at="2026-10-18T13:05:00+00:00",side="LONG",
        state_at_entry="CONFIRMED",daily_swing_candles_at_signal=120,plan=_plan())
    event=dict(signal_id=signal_id,event_type="TP1",event_at="2026-10-18T13:10:00+00:00",
               price=105.0,fraction_closed=0.3,pnl_usd=7.5,pnl_r=0.3,close_trade=False)
    assert repo.record_exit_event(**event) is True
    assert repo.record_exit_event(**event) is False
    with connect_pg() as conn:
        row=conn.execute("SELECT realized_pnl_usd,remaining_fraction FROM trade_signals WHERE id=%s",
                         (signal_id,)).fetchone()
        count=conn.execute("SELECT count(*) AS n FROM trade_events WHERE signal_id=%s AND event_type='TP1'",
                           (signal_id,)).fetchone()
    assert row["realized_pnl_usd"]==pytest.approx(7.5)
    assert row["remaining_fraction"]==pytest.approx(.7)
    assert count["n"]==1
