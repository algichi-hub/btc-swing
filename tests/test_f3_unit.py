"""F3: pure invariants and no scheduler on cloud API."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import ast
import pytest

from app.automation.cloud_worker import cycle_key,_safe_error,get_worker_health,run_once,INTERVAL_SECONDS

@pytest.mark.parametrize('minute', [0,1,4,5,9,59])
def test_slot_rounding_and_utc(minute):
    dt=datetime(2026,10,17,12,minute,13,tzinfo=timezone.utc)
    got=datetime.fromisoformat(cycle_key(dt))
    assert got.minute==minute//5*5
    assert got.second==0

@pytest.mark.parametrize('dt', [datetime(2026,3,29,0,59,tzinfo=timezone.utc), datetime(2026,10,25,1,1,tzinfo=timezone.utc)])
def test_dst_independent_utc_slots(dt):
    assert datetime.fromisoformat(cycle_key(dt)).tzinfo==timezone.utc

def test_naive_time_rejected():
    with pytest.raises(ValueError): cycle_key(datetime(2026,10,17))

def test_no_credential_leakage_in_error_code():
    assert _safe_error(ValueError('postgres://user:secret@server'))=='ValueError'
    assert _safe_error('postgres://user:secret@server')=='WorkerError'

def test_worker_requires_postgresql(monkeypatch):
    monkeypatch.setenv('BTC_DB_BACKEND','sqlite')
    with pytest.raises(RuntimeError,match='PostgreSQL'): run_once(lambda:True)

def test_telegram_disabled_in_cloud(monkeypatch):
    monkeypatch.setenv('BTC_DB_BACKEND','postgres')
    monkeypatch.setenv('TELEGRAM_ENABLED','true')
    with pytest.raises(RuntimeError,match='Telegram'): run_once(lambda:True)

def test_worker_is_separate_from_fastapi_lifespan():
    source=Path(__file__).resolve().parents[1]/'app/main.py'
    tree=ast.parse(source.read_text())
    assert 'BTC_PROCESS_ROLE' in source.read_text()
    assert 'automation_scheduler.start()' in source.read_text() # kept for local Raspberry

def test_deployment_uses_worker_command():
    dockerfile=(Path(__file__).resolve().parents[1]/'deploy/railway-worker.Dockerfile').read_text()
    assert 'app.automation.cloud_worker' in dockerfile
    assert 'python:3.11' in dockerfile