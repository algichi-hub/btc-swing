from __future__ import annotations

import sqlite3
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.auth.models import AuthSession, User, UserRole
from app.auth.repository import AuthRepository
from app.auth.security import (
    check_needs_rehash,
    derive_csrf_token,
    generate_session_token,
    hash_password,
    hash_session_token,
    normalize_username,
    validate_password_policy,
    verify_dummy_password,
    verify_password,
)
from app.config import settings
from app.storage.database import connect


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


class AuthService:
    """Service orchestrating authentication, password hashing, and session management."""

    def __init__(self, db_path: Path | None = None, repository: AuthRepository | None = None) -> None:
        self.db_path = db_path or settings.database_path
        self.repository = repository or AuthRepository()

    def create_user(
        self,
        username: str,
        password: str,
        role: str | UserRole = UserRole.ADMIN,
        enabled: bool = True,
    ) -> User:
        clean_username = normalize_username(username)
        validate_password_policy(password)

        role_enum = UserRole.from_str(role) if isinstance(role, str) else role
        pw_hash = hash_password(password)

        with connect(self.db_path) as conn:
            return self.repository.create_user(
                conn=conn,
                username=clean_username,
                password_hash=pw_hash,
                role=role_enum.value,
                enabled=enabled,
            )

    def authenticate(self, username: str, password: str) -> User | None:
        if not isinstance(username, str) or not isinstance(password, str):
            verify_dummy_password("dummy")
            return None
        try:
            clean_username = normalize_username(username)
        except ValueError:
            verify_dummy_password(password or "dummy")
            return None
        if not password:
            verify_dummy_password("dummy")
            return None

        with connect(self.db_path) as conn:
            user = self.repository.get_user_by_username(conn, clean_username)
            if user is None:
                verify_dummy_password(password)
                return None
            if not user.enabled:
                verify_dummy_password(password)
                return None
            if not verify_password(password, user.password_hash):
                return None

            if check_needs_rehash(user.password_hash):
                new_hash = hash_password(password)
                self.repository.update_password_hash(conn, user.id, new_hash)

            login_ts = _utc_now_iso()
            self.repository.update_last_login(conn, user.id, login_ts)
            return self.repository.get_user_by_id(conn, user.id)

    def check_login_rate_limits(
        self,
        canonical_username: str,
        client_ip: str,
        now: datetime | None = None,
    ) -> tuple[bool, int, str | None]:
        current_now = now or _utc_now()
        keys = [
            "global",
            f"ip:{client_ip}",
            f"user:{canonical_username}",
        ]
        with connect(self.db_path) as conn:
            return self.repository.check_login_rate_limits(conn, keys, current_now)

    def record_login_failure(
        self,
        canonical_username: str,
        client_ip: str,
        now: datetime | None = None,
    ) -> tuple[str, int, str | None]:
        current_now = now or _utc_now()
        buckets = [
            ("global", settings.auth_rate_limit_global_max, settings.auth_rate_limit_window_seconds, settings.auth_rate_limit_lockout_seconds),
            (f"ip:{client_ip}", settings.auth_rate_limit_ip_max, settings.auth_rate_limit_window_seconds, settings.auth_rate_limit_lockout_seconds),
            (f"user:{canonical_username}", settings.auth_rate_limit_user_max, settings.auth_rate_limit_window_seconds, settings.auth_rate_limit_lockout_seconds),
        ]
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self.repository.record_login_failure_atomic(conn, buckets, current_now)

    def reset_user_login_attempts(self, canonical_username: str) -> None:
        with connect(self.db_path) as conn:
            self.repository.reset_user_login_attempts(conn, canonical_username)

    def prune_stale_login_attempts(self, max_age_seconds: int = 86400) -> int:
        cutoff = (_utc_now() - timedelta(seconds=max_age_seconds)).isoformat()
        with connect(self.db_path) as conn:
            return self.repository.prune_stale_login_attempts(conn, cutoff)

    def derive_csrf_token(self, session: AuthSession) -> str:
        return derive_csrf_token(session.session_token_hash, settings.auth_csrf_secret)

    def change_password(self, user_id: int, current_password: str, new_password: str) -> bool:
        """Atomically rotate a password and revoke ALL sessions.

        Only the caller with a validated session should invoke this method.
        The old password must still match at the moment of the update.
        """
        if not isinstance(new_password, str) or len(new_password) < 16 or len(new_password) > 256:
            raise ValueError("La nueva contraseña debe tener entre 16 y 256 caracteres")
        if new_password == current_password:
            raise ValueError("La nueva contraseña debe ser diferente de la actual")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = self.repository.get_user_by_id(conn, user_id)
            if user is None or not user.enabled or not verify_password(current_password, user.password_hash):
                return False
            self.repository.update_password_hash(conn, user_id, hash_password(new_password))
            conn.execute("UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                         (_utc_now_iso(), user_id))
            return True

    @staticmethod
    def _recovery_hash(code: str) -> str:
        return hashlib.sha256(("btc-swing-recovery-v1:" + code).encode("ascii")).hexdigest()

    @staticmethod
    def _normalize_recovery_code(code: str) -> str | None:
        if not isinstance(code, str) or len(code) > 64:
            return None
        compact = re.sub(r"[-\\s]", "", code).lower()
        return compact if re.fullmatch(r"[0-9a-f]{32}", compact) else None

    def recovery_codes_remaining(self, user_id: int) -> int:
        with connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT count(*) AS total FROM auth_recovery_codes WHERE user_id = ? AND used_at IS NULL",
                (user_id,),
            ).fetchone()
            return int(result["total"])

    def generate_recovery_codes(self, user_id: int, password: str) -> list[str] | None:
        """Replace existing recovery codes after verifying current password."""
        if not isinstance(password, str) or len(password) > 256:
            return None
        codes = [secrets.token_hex(16) for _ in range(10)]
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            user = self.repository.get_user_by_id(conn, user_id)
            if user is None or not user.enabled or not verify_password(password, user.password_hash):
                return None
            conn.execute("DELETE FROM auth_recovery_codes WHERE user_id = ?", (user_id,))
            now = _utc_now_iso()
            for code in codes:
                conn.execute(
                    "INSERT INTO auth_recovery_codes(code_hash,user_id,created_at,used_at) VALUES(?,?,?,NULL)",
                    (self._recovery_hash(code), user_id, now),
                )
        return ["-".join(code[i:i+8] for i in range(0, 32, 8)) for code in codes]

    def _recovery_buckets(self, username: str, client_ip: str):
        # Separate from ordinary login lockouts; do not expose whether user exists.
        return [("recovery:global", 100, 3600, 900),
                ("recovery:user:" + username, 5, 900, 900),
                ("recovery:ip:" + client_ip, 15, 900, 900)]

    def recovery_is_locked(self, username: str, client_ip: str) -> tuple[bool, int]:
        with connect(self.db_path) as conn:
            keys = [entry[0] for entry in self._recovery_buckets(username, client_ip)]
            locked, retry, _ = self.repository.check_login_rate_limits(conn, keys, _utc_now())
            return locked, retry

    def reset_password_with_code(self, username: str, code: str, new_password: str,
                                 client_ip: str) -> str:
        """Return 'OK', 'INVALID' or 'LOCKED'; use a single transaction for one-use consume."""
        try:
            normalized = normalize_username(username)
        except (ValueError, TypeError):
            normalized = "invalid"
        if not isinstance(client_ip, str):
            client_ip = "unknown"
        buckets = self._recovery_buckets(normalized, client_ip)
        candidate = self._normalize_recovery_code(code)
        if not isinstance(new_password, str) or not 16 <= len(new_password) <= 256:
            return "INVALID"
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = _utc_now()
            locked, _, _ = self.repository.check_login_rate_limits(
                conn, [key for key, _, _, _ in buckets], now,
            )
            if locked:
                return "LOCKED"
            user = self.repository.get_user_by_username(conn, normalized)
            if user is not None and user.enabled and candidate is not None:
                digest = self._recovery_hash(candidate)
                row = conn.execute(
                    "SELECT code_hash FROM auth_recovery_codes WHERE user_id = ? AND code_hash = ? AND used_at IS NULL",
                    (user.id, digest),
                ).fetchone()
                if row is not None and hmac.compare_digest(row["code_hash"], digest):
                    updated = conn.execute(
                        "UPDATE auth_recovery_codes SET used_at = ? WHERE code_hash = ? AND used_at IS NULL",
                        (now.isoformat(), digest),
                    )
                    if updated.rowcount == 1:
                        self.repository.update_password_hash(conn, user.id, hash_password(new_password))
                        conn.execute(
                            "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                            (now.isoformat(), user.id),
                        )
                        conn.execute("DELETE FROM auth_login_attempts WHERE attempt_key = ?",
                                     ("recovery:user:" + normalized,))
                        return "OK"
            self.repository.record_login_failure_atomic(conn, buckets, now)
            return "INVALID"

    def create_session(
        self, user_id: int, ttl_hours: int | None = None
    ) -> tuple[AuthSession, str]:
        hours = ttl_hours if ttl_hours is not None else settings.auth_session_ttl_hours
        if hours <= 0:
            raise ValueError("Session TTL hours must be greater than zero")

        with connect(self.db_path) as conn:
            user = self.repository.get_user_by_id(conn, user_id)
            if user is None or not user.enabled:
                raise ValueError("User does not exist or is disabled")

            raw_token = generate_session_token()
            token_hash = hash_session_token(raw_token)
            expires_at = (_utc_now() + timedelta(hours=hours)).isoformat()

            session = self.repository.create_session(
                conn=conn,
                session_token_hash=token_hash,
                user_id=user_id,
                expires_at=expires_at,
            )
            return session, raw_token

    def validate_session(
        self, raw_token: str, now: datetime | None = None
    ) -> tuple[AuthSession, User] | None:
        if not isinstance(raw_token, str) or not raw_token.strip():
            return None

        current_now = now if now is not None else _utc_now()
        if current_now.tzinfo is None:
            current_now = current_now.replace(tzinfo=timezone.utc)

        token_hash = hash_session_token(raw_token.strip())

        with connect(self.db_path) as conn:
            session = self.repository.get_session_by_token_hash(conn, token_hash)
            if session is None:
                return None
            if session.is_revoked:
                return None

            try:
                expires_dt = datetime.fromisoformat(session.expires_at)
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None

            # Canonical expiration check: now >= expires_at is expired/invalid
            if current_now >= expires_dt:
                return None

            user = self.repository.get_user_by_id(conn, session.user_id)
            if user is None or not user.enabled:
                return None

            # Controlled last_seen_at update: only if elapsed >= touch interval
            try:
                last_seen_dt = datetime.fromisoformat(session.last_seen_at)
                if last_seen_dt.tzinfo is None:
                    last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
            except Exception:
                last_seen_dt = current_now - timedelta(seconds=settings.auth_session_touch_interval_seconds + 1)

            elapsed_seconds = (current_now - last_seen_dt).total_seconds()
            if elapsed_seconds >= settings.auth_session_touch_interval_seconds:
                now_iso = current_now.isoformat()
                self.repository.update_session_last_seen(conn, session.id, now_iso)
                updated_session = self.repository.get_session_by_id(conn, session.id) or session
                return updated_session, user

            return session, user

    def revoke_session(self, raw_token: str) -> bool:
        if not isinstance(raw_token, str) or not raw_token.strip():
            return False

        token_hash = hash_session_token(raw_token.strip())

        with connect(self.db_path) as conn:
            session = self.repository.get_session_by_token_hash(conn, token_hash)
            if session is None or session.is_revoked:
                return False
            return self.repository.revoke_session(conn, session.id)

    def revoke_session_by_id(self, session_id: int) -> bool:
        with connect(self.db_path) as conn:
            return self.repository.revoke_session(conn, session_id)

    def set_user_enabled(self, user_id: int, enabled: bool) -> None:
        with connect(self.db_path) as conn:
            self.repository.set_user_enabled(conn, user_id, enabled)

    def get_user_by_username(self, username: str) -> User | None:
        if not isinstance(username, str):
            return None
        try:
            clean_username = normalize_username(username)
        except ValueError:
            return None
        with connect(self.db_path) as conn:
            return self.repository.get_user_by_username(conn, clean_username)

    def get_user_by_id(self, user_id: int) -> User | None:
        with connect(self.db_path) as conn:
            return self.repository.get_user_by_id(conn, user_id)
