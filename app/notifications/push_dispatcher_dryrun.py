"""Deterministic F5 simulated per-device delivery; zero HTTP or VAPID dependencies.
G5 dispatcher will implement this contract with encrypted persistent device endpoints.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Callable

@dataclass
class Device:
    user_id: int
    endpoint_hash: str
    active: bool = True

@dataclass
class Delivery:
    event_id: str
    endpoint_hash: str
    status: str = "PENDING"
    attempts: int = 0
    due_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_code: str | None = None

class DryRunDispatcher:
    """No message can reach external providers. Provider is injected by tests."""
    def __init__(self, max_attempts: int = 4):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self.devices: dict[str, Device] = {}
        self.deliveries: dict[tuple[str,str], Delivery] = {}

    def subscribe_synthetic(self, user_id: int, fake_endpoint: str) -> Device:
        if user_id <= 0 or not fake_endpoint.startswith("test://"):
            raise ValueError("Only synthetic endpoints supported in F5-E0")
        digest = sha256(fake_endpoint.encode()).hexdigest()
        device = self.devices.get(digest)
        if device:
            if device.user_id != user_id:
                raise PermissionError("endpoint already assigned to another user")
            device.active = True
            return device
        device = Device(user_id, digest)
        self.devices[digest] = device
        return device

    def revoke(self, user_id: int, endpoint_hash: str) -> bool:
        d = self.devices.get(endpoint_hash)
        if d is None or d.user_id != user_id:
            return False
        d.active = False
        for row in self.deliveries.values():
            if row.endpoint_hash == endpoint_hash and row.status == "PENDING":
                row.status = "REVOKED"
        return True

    def stage(self, event_id: str, user_id: int) -> int:
        n = 0
        for endpoint_hash, device in self.devices.items():
            if device.user_id != user_id or not device.active:
                continue
            key = (event_id, endpoint_hash)
            if key not in self.deliveries:
                self.deliveries[key] = Delivery(event_id, endpoint_hash)
                n += 1
        return n

    def drain(self, synthetic_sender: Callable[[Delivery], bool], at: datetime | None = None) -> int:
        clock = at or datetime.now(timezone.utc)
        count = 0
        for row in self.deliveries.values():
            if row.status != "PENDING" or row.due_at > clock:
                continue
            device = self.devices.get(row.endpoint_hash)
            if not device or not device.active:
                row.status = "REVOKED"
                continue
            row.attempts += 1
            try:
                ok = bool(synthetic_sender(row))
            except Exception:
                ok = False
            if ok:
                row.status = "SENT"
                count += 1
            elif row.attempts >= self.max_attempts:
                row.status = "FAILED"
                row.error_code = "MAX_RETRIES"
            else:
                row.due_at = clock + timedelta(seconds=min(60 * (2 ** (row.attempts - 1)), 3600))
        return count
