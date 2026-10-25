"""P2 connection lifecycle regression without Neon credentials or network."""
import importlib
import sys
import types
from contextlib import contextmanager

import pytest


class DummyCursor:
    def fetchone(self):
        return {"value": 1}


class DummyConnection:
    def __init__(self):
        self.executed = []
    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        return DummyCursor()


class DummyPool:
    instances = []
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.conn = DummyConnection()
        self.entered = 0
        self.exited = []
        DummyPool.instances.append(self)
    @contextmanager
    def connection(self):
        self.entered += 1
        try:
            yield self.conn
        except Exception:
            self.exited.append("rollback")
            raise
        else:
            self.exited.append("commit")
    def close(self):
        self.closed = True


@pytest.fixture
def subject(monkeypatch):
    from app.storage import postgres
    postgres.close_api_pool()
    DummyPool.instances.clear()
    monkeypatch.setenv("BTC_PROCESS_ROLE", "api")
    monkeypatch.setenv("BTC_DATABASE_URL", "postgresql://test:test@neon.example/test")
    monkeypatch.delenv("BTC_TEST_DATABASE", raising=False)
    monkeypatch.setitem(sys.modules, "psycopg_pool", types.SimpleNamespace(ConnectionPool=DummyPool))
    yield postgres
    postgres.close_api_pool()


def test_pool_is_lazy_and_bounded(subject):
    assert not DummyPool.instances
    with subject.connect_pg() as conn:
        conn.execute("SELECT 1")
    with subject.connect_pg() as conn:
        conn.execute("SELECT 2")
    assert len(DummyPool.instances) == 1
    pool = DummyPool.instances[0]
    assert pool.kwargs["min_size"] == 0
    assert pool.kwargs["max_size"] == 2
    assert pool.entered == 2
    assert pool.exited == ["commit", "commit"]


def test_exception_returns_connection_with_rollback(subject):
    with pytest.raises(ValueError):
        with subject.connect_pg():
            raise ValueError("simulate failed transaction")
    assert DummyPool.instances[0].exited == ["rollback"]


def test_shutdown_closes_pool(subject):
    with subject.connect_pg():
        pass
    pool = DummyPool.instances[0]
    subject.close_api_pool()
    assert pool.closed is True
