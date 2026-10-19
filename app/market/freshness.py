"""Independent freshness control. Never use a processing timestamp as market-data proof."""
from datetime import datetime, timezone

MAX_HOURLY_AGE_SECONDS = 2 * 3600

def evaluate_hourly_freshness(candles, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware now required")
    if not candles:
        return {"status": "NO_DATA", "is_stale": True, "last_candle_close": None, "age_seconds": None}
    last_close_ms = max(int(c.close_time_ms) for c in candles)
    close = datetime.fromtimestamp(last_close_ms / 1000, timezone.utc)
    age = (now - close).total_seconds()
    status = "FUTURE_DATA" if age < -60 else ("STALE" if age > MAX_HOURLY_AGE_SECONDS else "FRESH")
    return {"status":status, "is_stale":status != "FRESH",
            "last_candle_close":close.isoformat(), "age_seconds":round(age, 1)}
