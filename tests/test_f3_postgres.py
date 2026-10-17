"""F3 isolated postgres tests; requires CI dedicated database ONLY."""
import os
from datetime import datetime,timezone,timedelta
from threading import Thread,Barrier
import pytest

@pytest.fixture(autouse=True)
def ephemeral_only():
    if os.getenv('BTC_TEST_DATABASE')!='YES' or os.getenv('BTC_DB_BACKEND')!='postgres':
        pytest.skip('Only ephemeral CI DB allowed')


def _now():return datetime(2026,10,17,12,0,tzinfo=timezone.utc)


def test_f3_migration_is_idempotent():
    from app.storage.worker_migration import apply_worker_migration
    assert apply_worker_migration() is True
    assert apply_worker_migration() is False


def test_f3_single_logical_cycle_and_skipped_repeat():
    from app.automation.cloud_worker import run_once,cycle_key
    calls=[]
    def do():calls.append('called');return True
    assert run_once(do,now=_now())=='OK'
    assert run_once(do,now=_now())=='SKIPPED'
    assert calls==['called']


def test_f3_worker_health_ok_and_stale():
    from app.automation.cloud_worker import get_worker_health
    assert get_worker_health()['status'] in ('OK','RETRASADO')
    assert get_worker_health(now=datetime.now(timezone.utc)+timedelta(hours=3))['status']=='RETRASADO'


def test_f3_durable_error_and_retry():
    from app.automation.cloud_worker import run_once,cycle_key
    now=_now()+timedelta(minutes=5)
    assert run_once(lambda:False,now=now)=='ERROR'
    assert run_once(lambda:True,now=now)=='OK'
    from app.storage.postgres import connect_pg
    with connect_pg() as db:
        row=db.execute('SELECT status,attempt FROM worker_cycles WHERE cycle_key=%s',(cycle_key(now),)).fetchone()
    assert row['status']=='OK' and row['attempt']==2


def test_f3_concurrent_workers_exactly_one_runs():
    from app.automation.cloud_worker import run_once
    import threading,time
    now=_now()+timedelta(minutes=10)
    barrier=Barrier(2); results=[];calls=[]
    def runner():
        barrier.wait()
        def work():calls.append(1);time.sleep(.25);return True
        results.append(run_once(work,now=now))
    a,b=Thread(target=runner),Thread(target=runner)
    a.start();b.start();a.join(timeout=10);b.join(timeout=10)
    assert not a.is_alive() and not b.is_alive()
    assert sorted(results)==['BUSY','OK']
    assert len(calls)==1


def test_f3_crash_stale_running_recovered():
    from app.storage.postgres import connect_pg
    from app.automation.cloud_worker import run_once,cycle_key
    now=_now()+timedelta(minutes=15)
    with connect_pg() as db:
        db.execute("INSERT INTO worker_cycles(cycle_key,status) VALUES(%s,'RUNNING')",(cycle_key(now),))
    assert run_once(lambda:True,now=now)=='OK'
    with connect_pg() as db:
        row=db.execute('SELECT status,attempt FROM worker_cycles WHERE cycle_key=%s',(cycle_key(now),)).fetchone()
    assert row['status']=='OK' and row['attempt']==2


def test_f3_failure_is_sanitized_and_heartbeat_reports_error():
    from app.storage.postgres import connect_pg
    from app.automation.cloud_worker import run_once,get_worker_health,cycle_key
    now=_now()+timedelta(minutes=20)
    def raise_secret():raise RuntimeError('postgres://user:secret@invalid-host')
    assert run_once(raise_secret,now=now)=='ERROR'
    assert get_worker_health()['status']=='ERROR'
    with connect_pg() as db:
        row=db.execute('SELECT error_code FROM worker_cycles WHERE cycle_key=%s',(cycle_key(now),)).fetchone()
        logs=db.execute("SELECT message FROM operational_logs WHERE code='CYCLE_FAILED' ORDER BY id DESC LIMIT 1").fetchone()
    assert row['error_code']=='RuntimeError'
    assert 'secret' not in logs['message']


def test_f3_no_external_orders_in_worker_source():
    from pathlib import Path
    src=(Path(__file__).resolve().parents[1]/'app/automation/cloud_worker.py').read_text().lower()
    for forbidden in ('place_order(', 'exchange.order(', 'submit_order('):assert forbidden not in src