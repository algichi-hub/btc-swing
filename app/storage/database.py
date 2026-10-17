from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS trade_opportunities (
    setup_id TEXT PRIMARY KEY,
    coin TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('LONG', 'SHORT')),
    support REAL NOT NULL,
    resistance REAL NOT NULL,
    origin_price REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE_UNTRADED', 'ACTIVE_TRADED', 'INVALIDATED')),
    created_at TEXT NOT NULL,
    executed_at TEXT,
    invalidated_at TEXT,
    invalidation_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_trade_opportunities_status
ON trade_opportunities (status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_opportunities_single_active
ON trade_opportunities (coin)
WHERE status IN ('ACTIVE_UNTRADED', 'ACTIVE_TRADED');

CREATE TABLE IF NOT EXISTS trade_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_id TEXT REFERENCES trade_opportunities(setup_id),
    created_at TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('BACKTEST','PAPER','LIVE')),
    side TEXT NOT NULL CHECK(side IN ('LONG','SHORT')),
    state_at_entry TEXT NOT NULL CHECK(state_at_entry IN ('NO_TRADE','WATCH','CONFIRMED','HIGH','VERY_HIGH')),
    daily_swing_candles_at_signal INTEGER,
    entry_reference REAL NOT NULL,
    stop_loss REAL NOT NULL,
    tp1 REAL NOT NULL,
    tp2 REAL NOT NULL,
    tp3 REAL NOT NULL,
    rr1 REAL NOT NULL,
    rr2 REAL NOT NULL,
    rr3 REAL NOT NULL,
    weighted_rr REAL NOT NULL,
    expectancy_r REAL,
    historical_win_rate REAL,
    statistical_samples INTEGER NOT NULL DEFAULT 0,
    margin_usd REAL NOT NULL,
    leverage INTEGER NOT NULL,
    notional_usd REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    fingerprint TEXT UNIQUE,
    tp1_hit_at TEXT,
    tp2_hit_at TEXT,
    tp3_hit_at TEXT,
    sl_hit_at TEXT,
    remaining_fraction REAL NOT NULL DEFAULT 1.0,
    realized_pnl_usd REAL NOT NULL DEFAULT 0.0,
    realized_r REAL NOT NULL DEFAULT 0.0,
    closed_at TEXT,
    last_processed_candle_close_ms INTEGER
);

CREATE TABLE IF NOT EXISTS trade_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL REFERENCES trade_signals(id) ON DELETE CASCADE,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    price REAL,
    fraction_closed REAL,
    pnl_usd REAL,
    pnl_r REAL
);

CREATE TABLE IF NOT EXISTS trade_results (
    signal_id INTEGER PRIMARY KEY REFERENCES trade_signals(id) ON DELETE CASCADE,
    closed_at TEXT,
    realized_pnl_usd REAL,
    realized_r REAL,
    max_favorable_excursion REAL,
    max_adverse_excursion REAL,
    holding_hours REAL
);

CREATE TABLE IF NOT EXISTS telegram_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    event_key TEXT NOT NULL UNIQUE,
    sent_at TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1 CHECK(success IN (0,1)),
    telegram_message_id TEXT,
    error_message TEXT,
    signal_id INTEGER REFERENCES trade_signals(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engine_runtime_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engine_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    price REAL,
    signal_state TEXT NOT NULL,
    signal_side TEXT,
    trade_window_open INTEGER NOT NULL CHECK(trade_window_open IN (0,1)),
    block_reason TEXT,
    setup_id TEXT,
    setup_active INTEGER NOT NULL DEFAULT 0 CHECK(setup_active IN (0,1)),
    snapshot_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_engine_snapshots_created_at
ON engine_snapshots (created_at);

CREATE INDEX IF NOT EXISTS idx_engine_snapshots_setup_id
ON engine_snapshots (setup_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_event_once_per_type
ON trade_events (signal_id, event_type);

CREATE INDEX IF NOT EXISTS idx_trade_signals_status
ON trade_signals (status);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'VIEWER')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash
ON auth_sessions (session_token_hash);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
ON auth_sessions (user_id);

CREATE TABLE IF NOT EXISTS auth_login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_key TEXT NOT NULL UNIQUE,
    failed_count INTEGER NOT NULL DEFAULT 0,
    first_failed_at TEXT NOT NULL,
    last_failed_at TEXT NOT NULL,
    locked_until TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_login_attempts_locked
ON auth_login_attempts (locked_until);
"""


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row["name"]) for row in rows]


def _migrate_trade_signals_schema(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "trade_signals")
    if not columns:
        return

    has_state_at_entry = "state_at_entry" in columns
    has_quality = "quality" in columns
    has_state = "state" in columns

    if has_state_at_entry and not has_quality and not has_state:
        return

    if has_state_at_entry:
        state_expr = "state_at_entry"
    elif has_state:
        state_expr = "state"
    elif has_quality:
        state_expr = (
            "CASE quality "
            "WHEN 'VERY_HIGH' THEN 'VERY_HIGH' "
            "WHEN 'HIGH' THEN 'HIGH' "
            "WHEN 'CONFIRMED' THEN 'CONFIRMED' "
            "WHEN 'WATCH' THEN 'WATCH' "
            "WHEN 'NO_TRADE' THEN 'NO_TRADE' "
            "WHEN 'MEDIUM' THEN 'CONFIRMED' "
            "WHEN 'LOW' THEN 'WATCH' "
            "ELSE 'WATCH' END"
        )
    else:
        state_expr = "'WATCH'"

    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.executescript(
            f"""
CREATE TABLE trade_signals_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('BACKTEST','PAPER','LIVE')),
    side TEXT NOT NULL CHECK(side IN ('LONG','SHORT')),
    state_at_entry TEXT NOT NULL CHECK(state_at_entry IN ('NO_TRADE','WATCH','CONFIRMED','HIGH','VERY_HIGH')),
    daily_swing_candles_at_signal INTEGER,
    entry_reference REAL NOT NULL,
    stop_loss REAL NOT NULL,
    tp1 REAL NOT NULL,
    tp2 REAL NOT NULL,
    tp3 REAL NOT NULL,
    rr1 REAL NOT NULL,
    rr2 REAL NOT NULL,
    rr3 REAL NOT NULL,
    weighted_rr REAL NOT NULL,
    expectancy_r REAL,
    historical_win_rate REAL,
    statistical_samples INTEGER NOT NULL DEFAULT 0,
    margin_usd REAL NOT NULL,
    leverage INTEGER NOT NULL,
    notional_usd REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    fingerprint TEXT UNIQUE,
    tp1_hit_at TEXT,
    tp2_hit_at TEXT,
    tp3_hit_at TEXT,
    sl_hit_at TEXT,
    remaining_fraction REAL NOT NULL DEFAULT 1.0,
    realized_pnl_usd REAL NOT NULL DEFAULT 0.0,
    realized_r REAL NOT NULL DEFAULT 0.0,
    closed_at TEXT,
    last_processed_candle_close_ms INTEGER
);

INSERT INTO trade_signals_new (
    id,
    created_at,
    origin,
    side,
    state_at_entry,
    daily_swing_candles_at_signal,
    entry_reference,
    stop_loss,
    tp1,
    tp2,
    tp3,
    rr1,
    rr2,
    rr3,
    weighted_rr,
    expectancy_r,
    historical_win_rate,
    statistical_samples,
    margin_usd,
    leverage,
    notional_usd,
    status,
    fingerprint,
    tp1_hit_at,
    tp2_hit_at,
    tp3_hit_at,
    sl_hit_at,
    remaining_fraction,
    realized_pnl_usd,
    realized_r,
    closed_at,
    last_processed_candle_close_ms
)
SELECT
    id,
    created_at,
    origin,
    side,
    {state_expr} AS state_at_entry,
    NULL,
    entry_reference,
    stop_loss,
    tp1,
    tp2,
    tp3,
    rr1,
    rr2,
    rr3,
    weighted_rr,
    expectancy_r,
    historical_win_rate,
    COALESCE(statistical_samples, 0),
    margin_usd,
    leverage,
    notional_usd,
    COALESCE(status, 'OPEN'),
    fingerprint,
    NULL,
    NULL,
    NULL,
    NULL,
    1.0,
    0.0,
    0.0,
    NULL,
    NULL
FROM trade_signals;

DROP TABLE trade_signals;
ALTER TABLE trade_signals_new RENAME TO trade_signals;
"""
        )
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    columns = _table_columns(conn, table_name)
    if column_name in columns:
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _ensure_trade_signal_columns(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "trade_signals", "setup_id", "TEXT REFERENCES trade_opportunities(setup_id)")
    _ensure_column(conn, "trade_signals", "daily_swing_candles_at_signal", "INTEGER")
    _ensure_column(conn, "trade_signals", "tp1_hit_at", "TEXT")
    _ensure_column(conn, "trade_signals", "tp2_hit_at", "TEXT")
    _ensure_column(conn, "trade_signals", "tp3_hit_at", "TEXT")
    _ensure_column(conn, "trade_signals", "sl_hit_at", "TEXT")
    _ensure_column(conn, "trade_signals", "remaining_fraction", "REAL NOT NULL DEFAULT 1.0")
    _ensure_column(conn, "trade_signals", "realized_pnl_usd", "REAL NOT NULL DEFAULT 0.0")
    _ensure_column(conn, "trade_signals", "realized_r", "REAL NOT NULL DEFAULT 0.0")
    _ensure_column(conn, "trade_signals", "closed_at", "TEXT")
    _ensure_column(conn, "trade_signals", "last_processed_candle_close_ms", "INTEGER")


def _ensure_trade_opportunities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_opportunities (
            setup_id TEXT PRIMARY KEY,
            coin TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('LONG', 'SHORT')),
            support REAL NOT NULL,
            resistance REAL NOT NULL,
            origin_price REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('ACTIVE_UNTRADED', 'ACTIVE_TRADED', 'INVALIDATED')),
            created_at TEXT NOT NULL,
            executed_at TEXT,
            invalidated_at TEXT,
            invalidation_reason TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trade_opportunities_status
        ON trade_opportunities (status)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_opportunities_single_active
        ON trade_opportunities (coin)
        WHERE status IN ('ACTIVE_UNTRADED', 'ACTIVE_TRADED')
        """
    )


def _ensure_trade_event_columns(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "trade_events", "fraction_closed", "REAL")


def _ensure_telegram_event_columns(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "telegram_events", "success", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "telegram_events", "telegram_message_id", "TEXT")
    _ensure_column(conn, "telegram_events", "error_message", "TEXT")


def _ensure_engine_runtime_state_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS engine_runtime_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _ensure_engine_snapshots_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS engine_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            price REAL,
            signal_state TEXT NOT NULL,
            signal_side TEXT,
            trade_window_open INTEGER NOT NULL CHECK(trade_window_open IN (0,1)),
            block_reason TEXT,
            setup_id TEXT,
            setup_active INTEGER NOT NULL DEFAULT 0 CHECK(setup_active IN (0,1)),
            snapshot_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_engine_snapshots_created_at
        ON engine_snapshots (created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_engine_snapshots_setup_id
        ON engine_snapshots (setup_id)
        """
    )


def _ensure_auth_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('ADMIN', 'VIEWER')),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            revoked_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash
        ON auth_sessions (session_token_hash)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
        ON auth_sessions (user_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_key TEXT NOT NULL UNIQUE,
            failed_count INTEGER NOT NULL DEFAULT 0,
            first_failed_at TEXT NOT NULL,
            last_failed_at TEXT NOT NULL,
            locked_until TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_login_attempts_locked
        ON auth_login_attempts (locked_until)
        """
    )


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def initialize(path: Path) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _migrate_trade_signals_schema(conn)
        _ensure_trade_opportunities_table(conn)
        _ensure_trade_signal_columns(conn)
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_signals_setup_id_unique
            ON trade_signals (setup_id) WHERE setup_id IS NOT NULL
            """
        )
        _ensure_trade_event_columns(conn)
        _ensure_telegram_event_columns(conn)
        _ensure_engine_runtime_state_table(conn)
        _ensure_engine_snapshots_table(conn)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_telegram_events_type_success
            ON telegram_events (event_type, success, sent_at)
            """
        )
        _ensure_auth_tables(conn)
