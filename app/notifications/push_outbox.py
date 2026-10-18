"""F5-E0 offline outbox domain; no networking or external delivery.
Persisted SQL and dispatcher integration are explicitly gated until G3/G4 GO.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Callable
import json

@dataclass
class Event:
    event_id: str
    kind: str
    payload: dict
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    delivered: bool = False

@dataclass
class SimulatedOutbox:
    events: dict[str, Event] = field(default_factory=dict)
    def enqueue(self, source_id: str, kind: str, payload: dict, ttl_seconds: int = 3600) -> Event:
        if not source_id or not kind or ttl_seconds <= 0:
            raise ValueError("Invalid event")
        # Avoid sensitive push payloads: no wallet, password, token or trade details.
        if payload != {"kind": "BTC_V5_TEST"}:
            raise ValueError("Only synthetic, nonprivate test payloads in F5-E0")
        key = sha256(json.dumps([source_id, kind], separators=(",",":")).encode()).hexdigest()
        if key not in self.events:
            now = datetime.now(timezone.utc)
            self.events[key] = Event(key, kind, dict(payload), now, now + timedelta(seconds=ttl_seconds))
        return self.events[key]
    def dispatch_simulated(self, callback: Callable[[Event], bool], now: datetime | None = None) -> int:
        clock = now or datetime.now(timezone.utc)
        successful = 0
        for event in self.events.values():
            if event.delivered or clock >= event.expires_at:
                continue
            event.attempts += 1
            if callback(event):
                event.delivered = True
                successful += 1
        return successful
