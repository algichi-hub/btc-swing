"""F0 integration smoke: isolated local SQLite and no external network.

This test checks FastAPI lifespan and schema initialization; it deliberately
stubs the live scheduler and recovery step to prevent outbound market calls.
It is NOT a proof that Railway or the live scheduler already work.
"""
import sqlite3
from unittest.mock import Mock

from fastapi.testclient import TestClient


def test_fastapi_lifespan_health_and_fresh_database(tmp_path, monkeypatch):
    import app.main as mod

    db = tmp_path / "fresh-v5-f0-smoke.db"
    monkeypatch.setattr(mod.settings_service, "database_path", db)
    monkeypatch.setattr(mod.trade_repository, "database_path", db)

    bootstrap = Mock()
    start = Mock()
    stop = Mock()

    monkeypatch.setattr(mod.automation_engine, "bootstrap", bootstrap)
    monkeypatch.setattr(mod.automation_scheduler, "start", start)
    monkeypatch.setattr(mod.automation_scheduler, "stop", stop)
    monkeypatch.setattr(mod, "recover_downtime_opportunity", Mock())

    with TestClient(mod.create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ok"
        assert db.exists()

        with sqlite3.connect(db) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            for table in ("trade_opportunities", "trade_signals",
                          "trade_events", "trade_results", "users",
                          "auth_sessions", "engine_runtime_state"):
                assert table in tables
            for table in ("trade_opportunities", "trade_signals",
                          "trade_results"):
                assert conn.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0

    bootstrap.assert_called_once()
    start.assert_called_once()
    stop.assert_called_once()
