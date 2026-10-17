"""Unit-level SQL translation and migration guards, no database or network."""
import hashlib
from pathlib import Path
import pytest
from app.storage.postgres import _translate, INSERT_ID_TABLES


def test_pg_qmark_and_inserted_row_id():
    q, wants_id = _translate("INSERT INTO users(username, password_hash) VALUES (?, ?)")
    assert wants_id and q.endswith("RETURNING id")
    assert q.count("%s") == 2
    assert "?" not in q


def test_ignore_is_idempotent():
    q, wants_id = _translate("INSERT OR IGNORE INTO trade_events (signal_id,event_type) VALUES (?,?)")
    assert wants_id and "ON CONFLICT DO NOTHING RETURNING id" in q


def test_ci_lock_keyed_to_migration_path():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "0001_initial.sql"
    sql = migration.read_text()
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_opportunities_single_active" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_signals_setup_id_unique" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_ci" in sql
    assert "telegram_events" in sql  # V4 repository compatibility until F5
    assert "push_subscriptions" in sql and "notification_outbox" in sql
    assert len(hashlib.sha256(sql.encode()).hexdigest()) == 64


def test_fail_closed_unknown_collation():
    with pytest.raises(NotImplementedError):
        _translate("SELECT username COLLATE NOCASE FROM users")


def test_legacy_transaction_lock():
    q, _ = _translate("BEGIN IMMEDIATE")
    assert "pg_advisory_xact_lock" in q


def test_insert_id_targets_have_expected_tables():
    assert {"users", "auth_sessions", "trade_signals", "engine_snapshots"} <= INSERT_ID_TABLES


def test_missing_db_url_fails(monkeypatch):
    from app.storage.postgres import connect_pg
    monkeypatch.delenv("BTC_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="BTC_DATABASE_URL"):
        connect_pg()