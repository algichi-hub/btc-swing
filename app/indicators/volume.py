from __future__ import annotations

from statistics import median

from app.models import Candle


def relative_volume(candles: list[Candle], period: int = 20) -> float | None:
    """Last CLOSED candle volume divided by the median of preceding closed candles."""
    if len(candles) < period + 1:
        return None
    baseline = [c.volume for c in candles[-(period + 1):-1]]
    base = median(baseline)
    return None if base <= 0 else candles[-1].volume / base
