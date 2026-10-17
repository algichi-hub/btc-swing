"""PostgreSQL integration tests on isolated CI postgres service.
Never run against an existing Neon production database.
"""
import os
import pytest

@pytest.fixture(scope="module", autouse=True)
def ensure_test_database():
    if os.getenv("BTC_TEST_DATABASE") != "YES":
        pytest.skip("Set BTC_TEST_DATABASE=YES only on dedicated test database")
    if os.getenv("BTC_DB_BACKEND") != "postgres":
        pytest.skip("Only tests postgres mode")
    from app.storage.postgres import initialize_pg
    initialize_pg()


def test_f2_schema_and_initial_empty():
    from app.storage.postgres import connect_pg
    with connect_pg() as conn:
        expected={"trade_signals", "trade_opportunities", "trade_events", "trade_results", "users", "auth_sessions", "auth_login_attempts", "app_settings", "engine_runtime_state", "engine_snapshots", "operational_logs", "worker_heartbeat", "notification_outbox", "push_subscriptions", "schema_migrations"}
        actual={row["table_name"] for row in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()}
        assert expected <= actual
        assert conn.execute("SELECT count(*) AS n FROM trade_signals").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM engine_snapshots").fetchone()["n"] == 0


def test_f2_idempotent_schema():
    from app.storage.postgres import initialize_pg, connect_pg
    initialize_pg(); initialize_pg()
    with connect_pg() as conn:
        assert conn.execute("SELECT count(*) AS n FROM schema_migrations WHERE version='0001_initial'").fetchone()["n"] == 1


def test_f2_repository_settings_and_state():
    from pathlib import Path
    from app.storage.trade_repository import TradeRepository
    from app.storage.postgres import connect_pg
    repo=TradeRepository(Path("unused.db"))
    repo.set_runtime_state("test-f2-state", "value")
    repo.set_runtime_state("test-f2-state", "newvalue")
    assert repo.get_runtime_state("test-f2-state")=="newvalue"
    with connect_pg() as conn:
        assert conn.execute("SELECT count(*) AS n FROM engine_runtime_state WHERE key=%s", ("test-f2-state",)).fetchone()["n"]==1


def test_f2_constraint_single_active_coin():
    from app.storage.postgres import connect_pg
    import psycopg
    import sqlite3
    with connect_pg() as conn:
        conn.execute("INSERT INTO trade_opportunities(setup_id,coin,side,support,resistance,origin_price,status,created_at) VALUES (?,?,?,?,?,?,?,?)", ("f2-active-1","BTC","LONG",90,110,100,"ACTIVE_UNTRADED","2026-10-17T00:00:00+00:00"))
    with pytest.raises(psycopg.errors.UniqueViolation):
        with connect_pg() as conn:
            conn.execute("INSERT INTO trade_opportunities(setup_id,coin,side,support,resistance,origin_price,status,created_at) VALUES (?,?,?,?,?,?,?,?)", ("f2-active-2","BTC","LONG",90,110,100,"ACTIVE_UNTRADED","2026-10-17T00:00:00+00:00"))


def test_f2_transaction_rollback():
    from app.storage.postgres import connect_pg
    with pytest.raises(RuntimeError):
        with connect_pg() as conn:
            conn.execute("INSERT INTO engine_runtime_state(key,value,updated_at) VALUES(?,?,?)", ("f2-rollback", "TEMP", "2026-10-17T00:00:00+00:00"))
            raise RuntimeError("simulate failure")
    with connect_pg() as conn:
        assert conn.execute("SELECT count(*) AS n FROM engine_runtime_state WHERE key=%s", ("f2-rollback",)).fetchone()["n"]==0


def test_f2_admin_bootstrap_and_duplicate():
    from app.storage.bootstrap import provision_admin
    from app.storage.postgres import connect_pg
    import psycopg
    import sqlite3
    id_=provision_admin("f2Admin", "passphrase-for-f2-tests-2026")
    assert id_>0
    with pytest.raises(RuntimeError,match="users already exist"):
        provision_admin("new-admin", "passphrase-for-f2-tests-2026")
    with connect_pg() as conn:
        assert conn.execute("SELECT role FROM users WHERE id=%s", (id_,)).fetchone()["role"]=="ADMIN"
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO users(username,password_hash,role,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?)", ("F2ADMIN","hash","ADMIN",1,"now","now"))


def test_f2_foreign_key_and_event_idempotency():
    from app.storage.postgres import connect_pg
    import psycopg
    import sqlite3
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connect_pg() as conn:
            conn.execute("INSERT INTO trade_events(signal_id,event_at,event_type) VALUES(?,?,?)", (99999,"now","TP1"))


def test_f2_adapter_translations():
    from app.storage.postgres import _translate
    assert "RETURNING id" in _translate("INSERT OR IGNORE INTO trade_signals (id) VALUES (?)")[0]
    assert "ON CONFLICT DO NOTHING" in _translate("INSERT OR IGNORE INTO trade_events (signal_id) VALUES (?)")[0]
    assert "lower(username) = lower(%s)" in _translate("SELECT * FROM users WHERE username = ? COLLATE NOCASE")[0]
    assert "pg_advisory_xact_lock" in _translate("BEGIN IMMEDIATE")[0]


def test_f2_trade_repository_insert_and_dedup():
    from pathlib import Path
    from app.storage.trade_repository import TradeRepository
    repo = TradeRepository(Path('unused-in-postgres.db'))
    plan = dict(entry=100.0, sl=95.0, tp1=105.0, tp2=110.0, tp3=115.0,
                rr1=1.0, rr2=2.0, rr3=3.0, weighted_rr=2.1,
                margin_usd=100.0, leverage=5, notional_usd=500.0)
    params = dict(fingerprint='f2-trade-fingerprint', created_at='2026-10-17T12:00:00+00:00',
                  side='LONG', state_at_entry='CONFIRMED', daily_swing_candles_at_signal=120,
                  plan=plan)
    one = repo.create_paper_trade(**params)
    two = repo.create_paper_trade(**params)
    assert isinstance(one, int) and one > 0 and one == two
    assert repo.count_open_trades() == 1
    assert any(int(row['id']) == one for row in repo.list_open_trades())


def test_f2_existing_v4_auth_repo_and_session():
    from app.auth.repository import AuthRepository
    from app.storage.postgres import connect_pg
    from app.auth.security import hash_password, verify_password
    repo = AuthRepository()
    with connect_pg() as conn:
        user = repo.create_user(conn, 'F2-viewer', hash_password('long-f2-viewer-password'), 'VIEWER')
        assert user.id > 0
        looked = repo.get_user_by_username(conn, 'f2-VIEWER')
        assert looked is not None and looked.id == user.id and looked.role == 'VIEWER'
        assert verify_password('long-f2-viewer-password', looked.password_hash)
        session = repo.create_session(conn, 'f2-synthetic-token-hash', user.id,
                                      '2027-01-01T00:00:00+00:00')
        assert session.id > 0
        assert repo.get_session_by_token_hash(conn, 'f2-synthetic-token-hash').id == session.id
        assert repo.revoke_session(conn, session.id)
        assert not repo.revoke_session(conn, session.id)


def test_f2_outbox_unique_and_logging():
    from app.storage.postgres import connect_pg
    with connect_pg() as conn:
        first = conn.execute("INSERT INTO notification_outbox(event_key,event_type,payload) VALUES(?,?,?) ON CONFLICT(event_key) DO NOTHING RETURNING id",
                             ('f2-idempotence', 'SIGNAL', '{}')).fetchone()
        second = conn.execute("INSERT INTO notification_outbox(event_key,event_type,payload) VALUES(?,?,?) ON CONFLICT(event_key) DO NOTHING RETURNING id",
                              ('f2-idempotence', 'SIGNAL', '{}')).fetchone()
        assert first is not None and second is None
        assert conn.execute("SELECT count(*) AS n FROM notification_outbox WHERE event_key=%s", ('f2-idempotence',)).fetchone()['n'] == 1
        conn.execute("INSERT INTO operational_logs(service,severity,code,message) VALUES(?,?,?,?)", ('engine', 'INFO', 'F2', 'synthetic smoke'))
        assert conn.execute("SELECT count(*) AS n FROM operational_logs WHERE code=%s", ('F2',)).fetchone()['n'] == 1


def test_f2_parallel_transaction_conflict_single_active():
    from app.storage.postgres import connect_pg
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from psycopg.errors import UniqueViolation
    barrier = Barrier(2)
    def attempt(i):
        barrier.wait(timeout=10)
        try:
            with connect_pg() as conn:
                conn.execute("INSERT INTO trade_opportunities(setup_id,coin,side,support,resistance,origin_price,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
                             (f'f2-race-{i}', 'ETH', 'LONG', 90, 110, 100, 'ACTIVE_UNTRADED', '2026-10-17T00:00:00+00:00'))
            return 'inserted'
        except UniqueViolation:
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,[1,2]))
    assert sorted(results)==['inserted','rejected']
    with connect_pg() as conn:
        assert conn.execute("SELECT count(*) AS n FROM trade_opportunities WHERE coin=%s AND status='ACTIVE_UNTRADED'", ('ETH',)).fetchone()['n']==1

def test_f2_least_privilege_roles():
    from app.storage.postgres import connect_pg
    with connect_pg() as conn:
        rows = conn.execute("""
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole,
                   pg_has_role(rolname, 'pg_database_owner', 'MEMBER') AS db_owner,
                   (SELECT rolpassword IS NULL FROM pg_authid WHERE pg_authid.rolname = pg_roles.rolname) AS password_unset
            FROM pg_roles
            WHERE rolname IN ('btc_v5_engine_app','btc_v5_web_app')
            ORDER BY rolname
        """).fetchall()
        assert len(rows) == 2
        assert all(not row['rolsuper'] and not row['rolcreatedb'] and not row['rolcreaterole'] for row in rows)
        assert all(row['password_unset'] for row in rows)
        assert conn.execute("SELECT has_table_privilege('btc_v5_engine_app','trade_signals','INSERT') AS allowed").fetchone()['allowed']
        assert not conn.execute("SELECT has_table_privilege('btc_v5_web_app','trade_signals','INSERT') AS allowed").fetchone()['allowed']
        assert not conn.execute("SELECT has_table_privilege('btc_v5_engine_app','auth_sessions','INSERT') AS allowed").fetchone()['allowed']
        assert conn.execute("SELECT has_table_privilege('btc_v5_web_app','auth_sessions','INSERT') AS allowed").fetchone()['allowed']


def test_f2_settings_defaults_seed_and_idempotence():
    from pathlib import Path
    from app.settings.service import SettingsService
    from app.storage.postgres import connect_pg
    service = SettingsService(Path('unused-on-postgres.db'), 120, 730)
    service.apply_defaults()
    service.apply_defaults()
    settings = service.get_all()
    assert settings['volume_confirmation_threshold'] == 1.05
    assert settings['daily_swing_candles'] == 120
    with connect_pg() as conn:
        assert conn.execute('SELECT count(*) AS n FROM app_settings').fetchone()['n'] == len(settings)
