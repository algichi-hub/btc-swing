from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def open_time_iso(self) -> str:
        return datetime.fromtimestamp(self.open_time_ms / 1000, tz=timezone.utc).isoformat()
