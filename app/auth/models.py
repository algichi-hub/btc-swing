from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"

    @classmethod
    def from_str(cls, value: str) -> UserRole:
        upper = value.strip().upper()
        if upper == cls.ADMIN.value:
            return cls.ADMIN
        if upper == cls.VIEWER.value:
            return cls.VIEWER
        raise ValueError(f"Invalid role: '{value}'. Allowed roles are: {cls.ADMIN.value}, {cls.VIEWER.value}")


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    role: str
    enabled: bool
    created_at: str
    updated_at: str
    last_login_at: str | None = None

    def __repr__(self) -> str:
        return (
            f"User(id={self.id}, username={self.username!r}, "
            f"role={self.role!r}, enabled={self.enabled}, "
            f"created_at={self.created_at!r}, updated_at={self.updated_at!r}, "
            f"last_login_at={self.last_login_at!r}, password_hash='***')"
        )

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
        }


@dataclass(frozen=True)
class AuthSession:
    id: int
    session_token_hash: str
    user_id: int
    created_at: str
    expires_at: str
    last_seen_at: str
    revoked_at: str | None = None

    def __repr__(self) -> str:
        return (
            f"AuthSession(id={self.id}, user_id={self.user_id}, "
            f"created_at={self.created_at!r}, expires_at={self.expires_at!r}, "
            f"last_seen_at={self.last_seen_at!r}, revoked_at={self.revoked_at!r}, "
            f"session_token_hash='***')"
        )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
