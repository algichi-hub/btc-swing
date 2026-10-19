from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from app.market.freshness import evaluate_hourly_freshness

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)

def candle_close(seconds_ago):
    return SimpleNamespace(close_time_ms=int((NOW-timedelta(seconds=seconds_ago)).timestamp()*1000))

def test_recent_candle_passes():
    result=evaluate_hourly_freshness([candle_close(3600)],now=NOW)
    assert result["status"] == "FRESH" and result["is_stale"] is False

def test_old_candle_fails_even_if_worker_ok():
    result=evaluate_hourly_freshness([candle_close(10800)],now=NOW)
    assert result["status"] == "STALE" and result["is_stale"] is True

def test_missing_candle_fails_closed():
    assert evaluate_hourly_freshness([],now=NOW)["status"] == "NO_DATA"

def test_future_candle_fails_closed():
    assert evaluate_hourly_freshness([candle_close(-3600)],now=NOW)["status"] == "FUTURE_DATA"

def test_most_recent_close_used_not_collection_order():
    data=[candle_close(3600),candle_close(10800)]
    assert evaluate_hourly_freshness(data,now=NOW)["status"] == "FRESH"
