"""History/PnL read-only functional and regression tests; no engine or live DB."""
from datetime import datetime, timedelta, timezone

import pytest

from app.storage.database import connect, initialize
from app.storage.trade_repository import TradeRepository


@pytest.fixture
def fixture_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BTC_DB_BACKEND", "sqlite")
    db = tmp_path / "history-test.sqlite3"
    initialize(db)
    return db, TradeRepository(db)


def add_trade(db, signal_id, created_at, status="OPEN", closed_at=None, pnl=0.0):
    with connect(db) as conn:
        conn.execute(
            """INSERT INTO trade_signals (
              id, created_at, origin, side, state_at_entry, entry_reference,
              stop_loss, tp1, tp2, tp3, rr1, rr2, rr3, weighted_rr,
              margin_usd, leverage, notional_usd, status, closed_at,
              realized_pnl_usd
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (signal_id, created_at, "PAPER", "LONG", "HIGH", 100,
             95, 105, 110, 115, 1, 2, 3, 2, 100, 2, 200,
             status, closed_at, pnl),
        )


def add_event(db, signal_id, at, event_type, pnl):
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO trade_events(signal_id, event_at, event_type, pnl_usd) VALUES (?,?,?,?)",
            (signal_id, at, event_type, pnl),
        )


def test_open_trades_are_visible_and_events_are_ordered(fixture_db):
    db, repository = fixture_db
    add_trade(db, 1, "2026-10-22T10:00:00+00:00", "CLOSED", "2026-10-23T00:00:00+00:00")
    add_trade(db, 2, "2026-11-04T10:00:00+00:00")
    add_event(db, 2, "2026-11-04T15:04:59+00:00", "TP1", 12.62815)
    records = repository.list_trade_history(100)
    assert [r["id"] for r in records] == [2, 1]
    assert [r["status"] for r in records] == ["OPEN", "CLOSED"]
    assert [r["event_type"] for r in repository.list_trade_events(2)] == ["TP1"]


def test_realized_partial_pnl_once_and_flat_days(fixture_db):
    db, repository = fixture_db
    add_trade(db, 4, "2026-11-03T09:00:00+00:00", pnl=12.62815)
    add_event(db, 4, "2026-11-04T15:04:59+00:00", "TP1", 12.62815)
    points = repository.get_daily_cumulative_pnl(to_date="2026-11-06")
    assert [p["date"] for p in points] == ["2026-11-04", "2026-11-05", "2026-11-06"]
    assert [p["daily_pnl"] for p in points] == [12.63, 0, 0]
    assert [p["cumulative_pnl"] for p in points] == [12.63, 12.63, 12.63]
    assert [p["trade_count"] for p in points] == [1, 0, 0]


def test_closed_trade_partial_exits_no_double_count(fixture_db):
    db, repository = fixture_db
    add_trade(db, 3, "2026-10-25T00:00:00+00:00", "CLOSED",
              "2026-10-30T00:04:59+00:00", pnl=-13.4664892587)
    add_event(db, 3, "2026-10-29T15:49:59+00:00", "TP1", 6.8406514121)
    add_event(db, 3, "2026-10-30T00:04:59+00:00", "SL", -20.3071406708)
    points = repository.get_daily_cumulative_pnl(to_date="2026-10-31")
    assert [p["daily_pnl"] for p in points] == [6.84, -20.31, 0.0]
    assert points[-1]["cumulative_pnl"] == -13.47
    assert repository.get_daily_cumulative_pnl(days=1, to_date="2026-10-31")[0]["cumulative_pnl"] == -13.47


def test_legacy_closed_without_events_falls_back_once(fixture_db):
    db, repository = fixture_db
    add_trade(db, 1, "2026-10-20T00:00:00+00:00", "CLOSED",
              "2026-10-21T00:00:00+00:00", pnl=-10)
    add_trade(db, 2, "2026-10-22T00:00:00+00:00")
    points = repository.get_daily_cumulative_pnl(to_date="2026-10-22")
    assert points[-1]["cumulative_pnl"] == -10.0
    assert sum(p["trade_count"] for p in points) == 1


def test_two_exits_same_day_count_one_trade(fixture_db):
    db, repository = fixture_db
    add_trade(db, 9, "2026-10-28T00:00:00+00:00", "CLOSED",
              "2026-10-29T15:00:00+00:00", pnl=9)
    add_event(db, 9, "2026-10-29T10:00:00+00:00", "TP1", 3)
    add_event(db, 9, "2026-10-29T15:00:00+00:00", "TP2", 6)
    point = repository.get_daily_cumulative_pnl(to_date="2026-10-29")[-1]
    assert point["daily_pnl"] == 9
    assert point["trade_count"] == 1


def test_empty_no_trades_keeps_empty_chart(fixture_db):
    _, repository = fixture_db
    assert repository.list_trade_history() == []
    assert repository.get_daily_cumulative_pnl() == []


def test_default_series_reaches_current_utc_day(fixture_db):
    db, repository = fixture_db
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    add_trade(db, 1, yesterday.isoformat() + "T08:00:00+00:00")
    add_event(db, 1, yesterday.isoformat() + "T09:00:00+00:00", "TP1", 1.25)
    points = repository.get_daily_cumulative_pnl(days=7)
    assert points[-1]["date"] == datetime.now(timezone.utc).date().isoformat()
    assert points[-1]["cumulative_pnl"] == 1.25
