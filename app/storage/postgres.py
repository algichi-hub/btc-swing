"""Postgres backend with the minimum SQLite-call-site compatibility layer.

F2 is a persistence change only. SQL placeholders, SQLite's INSERT OR IGNORE,
`BEGIN IMMEDIATE`, and the few `lastrowid` paths are translated explicitly.
The current V4 backend remains the default until BTC_DB_BACKEND=postgres.
"""
from __future__ import annotations

import os
import hashlib
from urllib.parse import urlparse
import re
import sqlite3
from pathlib import Path
from typing import Any

INSERT_ID_TABLES = frozenset({
    "users", "auth_sessions", "auth_login_attempts", "trade_signals",
    "trade_events", "engine_snapshots", "telegram_events",
})


def _translate(sql: str) -> tuple[str, bool]:
    original = sql.strip()
    if original.upper() == "BEGIN IMMEDIATE":
        return "SELECT pg_advisory_xact_lock(5022026)", False
    ignore = bool(re.match(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", original))
    out = re.sub(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql)
    out = re.sub(r"(?is)username\s*=\s*\?\s+COLLATE\s+NOCASE", "lower(username) = lower(?)", out)
    if "COLLATE NOCASE" in out.upper():
        raise NotImplementedError("SQLite COLLATE NOCASE requires an explicit PostgreSQL translation")
    # All V4 user SQL uses positional qmark placeholders and never JSON ? operators.
    out = out.replace("?", "%s").rstrip().rstrip(";")
    if ignore:
        out += " ON CONFLICT DO NOTHING"
    match = re.match(r"(?is)^\s*INSERT\s+INTO\s+(\w+)\b", out)
    wants_id = bool(match and match.group(1).lower() in INSERT_ID_TABLES)
    if wants_id and not re.search(r"\bRETURNING\b", out, flags=re.I):
        out += " RETURNING id"
    return out, wants_id


class PgResult:
    def __init__(self, cursor: Any, lastrowid: int | None = None):
        self._cursor = cursor
        self.lastrowid = lastrowid
        self.rowcount = cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class PgConnection:
    def __init__(self, connection: Any):
        self.raw = connection

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, *args):
        return self.raw.__exit__(*args)

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> PgResult:
        sql, has_id = _translate(query)
        try:
            cur = self.raw.execute(sql, params)
        except Exception as exc:
            # Preserve the V4 domain error contract for duplicate users.
            try:
                import psycopg
                if isinstance(exc, psycopg.errors.UniqueViolation) and re.match(r"(?is)^\s*INSERT\s+INTO\s+users\b", sql):
                    raise sqlite3.IntegrityError("UNIQUE constraint failed: users.username") from exc
            except ImportError:
                pass
            raise
        lastrowid = None
        if has_id:
            row = cur.fetchone()
            if row is not None:
                lastrowid = int(row["id"])
        return PgResult(cur, lastrowid)


def connect_pg() -> PgConnection:
    url = os.environ.get("BTC_DATABASE_URL")
    if not url:
        raise RuntimeError("BTC_DATABASE_URL must be set for BTC_DB_BACKEND=postgres")
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        raise RuntimeError("BTC_DATABASE_URL must be a PostgreSQL connection URL")
    import psycopg
    from psycopg.rows import dict_row
    host = urlparse(url).hostname or ""
    # TLS required for Neon; the ephemeral CI postgres:17 service has no TLS.
    ci_local = os.getenv("BTC_TEST_DATABASE") == "YES" and host in {"localhost", "127.0.0.1"}
    return PgConnection(psycopg.connect(url, row_factory=dict_row,
                connect_timeout=10, sslmode="disable" if ci_local else "require"))


def initialize_pg() -> None:
    """Idempotent first install, checksum guard and atomic migration transaction.

    The schema can be installed only into a *new* V5 database. No ETL.
    Concurrent startups serialize through advisory transaction lock.
    """
    sql = (Path(__file__).resolve().parents[2] / "migrations" / "0001_initial.sql").read_text()
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    statements = [q.strip() for q in "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    ).split(";") if q.strip()]
    with connect_pg() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(5022026)")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        # Handles Preview DDL bootstrapped before checksum tracking was added.
        conn.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT")
        row = conn.execute("SELECT checksum FROM schema_migrations WHERE version = %s", ("0001_initial",)).fetchone()
        if row is not None and row["checksum"] is not None and row["checksum"] != checksum:
            raise RuntimeError("Migration checksum mismatch for 0001_initial")
        for statement in statements:
            conn.execute(statement)
        conn.execute("INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s) ON CONFLICT(version) DO UPDATE SET checksum=EXCLUDED.checksum WHERE schema_migrations.checksum IS NULL", ("0001_initial", checksum))