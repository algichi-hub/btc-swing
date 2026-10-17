"""F4 operations log API: authentication, pagination, redaction and stale health."""
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import operations
from app.auth.http import require_authenticated


class FakeConnection:
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def execute(self, sql, params=()):
        self.last_sql = sql
        self.last_params = params
        if "count(*) AS total" in sql: return FakeResult([{"total": 2}])
        if "count(*) AS errors_24h" in sql: return FakeResult([{"errors_24h": 1}])
        if "FROM worker_cycles" in sql:
            return FakeResult([{"status": "OK", "cycle_key": "2026-10-17T12:00:00+00:00",
                                "started_at": datetime(2026,10,17,12,tzinfo=timezone.utc),
                                "completed_at": datetime(2026,10,17,12,0,15,tzinfo=timezone.utc),
                                "error_code": None}])
        return FakeResult([
            {"id": 2, "created_at": datetime(2026,10,17,12,tzinfo=timezone.utc),
             "service": "btc-v5-engine", "severity": "ERROR", "cycle_key": "slot",
             "code": "HTTP_TIMEOUT", "message": "postgres://u:secret@example"},
            {"id": 1, "created_at": datetime(2026,10,17,11,tzinfo=timezone.utc),
             "service": "btc-v5-engine", "severity": "INFO", "cycle_key": "slot",
             "code": "CYCLE_COMPLETED", "message": "OK"},
        ])


class FakeResult:
    def __init__(self, rows): self.rows=rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


@pytest.fixture
def client(monkeypatch):
    app=FastAPI()
    app.include_router(operations.router)
    monkeypatch.setattr(operations, "connect_pg", lambda: FakeConnection())
    monkeypatch.setattr(operations, "get_worker_health", lambda **kw: {
        "status": "RETRASADO", "age_seconds": 677,
        "last_seen_at": "2026-10-17T12:00:00+00:00",
        "last_success_at": "2026-10-17T11:55:00+00:00",
        "cycle_key": "slot"
    })
    return app, TestClient(app)


def test_unauthenticated_denied(client):
    _,c=client
    assert c.get("/api/ops/logs").status_code == 401
    assert c.get("/api/ops/status").status_code == 401


def test_authenticated_viewer_can_read(client):
    app,c=client
    app.dependency_overrides[require_authenticated] = lambda: object()
    response=c.get("/api/ops/status")
    assert response.status_code == 200
    data=response.json()
    assert data["worker"]["status"] == "RETRASADO"
    assert data["last_cycle"]["status"] == "OK"
    assert data["errors_24h"] == 1
    assert data["source"] == "neon"


def test_log_pagination_and_redaction(client):
    app,c=client
    app.dependency_overrides[require_authenticated] = lambda: object()
    result=c.get("/api/ops/logs?page=2&page_size=10&severity=ERROR&service=btc-v5-engine")
    assert result.status_code == 200
    payload=result.json()
    assert payload["page"] == 2 and payload["total"] == 2
    assert payload["items"][0]["message"] == "[REDACTED]"
    assert "secret" not in str(payload)
    assert payload["items"][1]["message"] == "OK"


@pytest.mark.parametrize("query", ["page=0", "page_size=101", "severity=DEBUG",
                                     "service=hack", "page=wrong"])
def test_invalid_filters_rejected(client,query):
    app,c=client
    app.dependency_overrides[require_authenticated] = lambda: object()
    assert c.get("/api/ops/logs?"+query).status_code == 422


@pytest.mark.parametrize("raw", ["Authorization: Bearer abc", "password = foo",
                                  "https://api.example/foo", "api_key=blah"])
def test_redaction_contract(raw):
    assert operations._sanitize_message(raw) == "[REDACTED]"


def test_control_character_and_code_sanitizing():
    assert operations._sanitize_message("ready\nhello") == "ready hello"
    assert operations._sanitize_code("SQL;DROP TABLE") == "REDACTED"
