from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone

from app.auth.models import AuthSession, User


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=int(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        enabled=bool(row["enabled"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_login_at=str(row["last_login_at"]) if row["last_login_at"] is not None else None,
    )


def _row_to_session(row: sqlite3.Row) -> AuthSession:
    return AuthSession(
        id=int(row["id"]),
        session_token_hash=str(row["session_token_hash"]),
        user_id=int(row["user_id"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        last_seen_at=str(row["last_seen_at"]),
        revoked_at=str(row["revoked_at"]) if row["revoked_at"] is not None else None,
    )


class AuthRepository:
    """SQLite persistence repository for users and server-side sessions."""

    # -------------------------------------------------------------------------
    # User Operations
    # -------------------------------------------------------------------------

    def create_user(
        self,
        conn: sqlite3.Connection,
        username: str,
        password_hash: str,
        role: str,
        enabled: bool = True,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> User:
        now = _utc_now_iso()
        c_at = created_at or now
        u_at = updated_at or now
        enabled_int = 1 if enabled else 0

        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, password_hash, role, enabled_int, c_at, u_at),
            )
            user_id = cursor.lastrowid
            if user_id is None:
                raise RuntimeError("Failed to retrieve lastrowid after inserting user")
            return User(
                id=user_id,
                username=username,
                password_hash=password_hash,
                role=role,
                enabled=enabled,
                created_at=c_at,
                updated_at=u_at,
                last_login_at=None,
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: users.username" in str(exc) or "unique" in str(exc).lower():
                raise ValueError(f"Username '{username}' already exists") from exc
            raise

    def get_user_by_id(self, conn: sqlite3.Connection, user_id: int) -> User | None:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row is not None else None

    def get_user_by_username(self, conn: sqlite3.Connection, username: str) -> User | None:
        row = conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
        return _row_to_user(row) if row is not None else None

    def update_last_login(self, conn: sqlite3.Connection, user_id: int, last_login_at: str) -> None:
        conn.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (last_login_at, last_login_at, user_id),
        )

    def update_password_hash(self, conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
        now = _utc_now_iso()
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, now, user_id),
        )

    def set_user_enabled(self, conn: sqlite3.Connection, user_id: int, enabled: bool) -> None:
        now = _utc_now_iso()
        conn.execute(
            "UPDATE users SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, now, user_id),
        )

    def list_users(self, conn: sqlite3.Connection) -> list[User]:
        rows = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
        return [_row_to_user(r) for r in rows]

    # -------------------------------------------------------------------------
    # Session Operations
    # -------------------------------------------------------------------------

    def create_session(
        self,
        conn: sqlite3.Connection,
        session_token_hash: str,
        user_id: int,
        expires_at: str,
        created_at: str | None = None,
        last_seen_at: str | None = None,
    ) -> AuthSession:
        now = _utc_now_iso()
        c_at = created_at or now
        ls_at = last_seen_at or c_at

        cursor = conn.execute(
            """
            INSERT INTO auth_sessions (session_token_hash, user_id, created_at, expires_at, last_seen_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (session_token_hash, user_id, c_at, expires_at, ls_at),
        )
        session_id = cursor.lastrowid
        if session_id is None:
            raise RuntimeError("Failed to retrieve lastrowid after inserting session")
        return AuthSession(
            id=session_id,
            session_token_hash=session_token_hash,
            user_id=user_id,
            created_at=c_at,
            expires_at=expires_at,
            last_seen_at=ls_at,
            revoked_at=None,
        )

    def get_session_by_token_hash(
        self, conn: sqlite3.Connection, session_token_hash: str
    ) -> AuthSession | None:
        row = conn.execute(
            "SELECT * FROM auth_sessions WHERE session_token_hash = ?",
            (session_token_hash,),
        ).fetchone()
        return _row_to_session(row) if row is not None else None

    def get_session_by_id(self, conn: sqlite3.Connection, session_id: int) -> AuthSession | None:
        row = conn.execute("SELECT * FROM auth_sessions WHERE id = ?", (session_id,)).fetchone()
        return _row_to_session(row) if row is not None else None

    def revoke_session(
        self, conn: sqlite3.Connection, session_id: int, revoked_at: str | None = None
    ) -> bool:
        """Revokes a session by ID. Idempotent: returns True if newly revoked, False if already revoked."""
        r_at = revoked_at or _utc_now_iso()
        cursor = conn.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (r_at, session_id),
        )
        return cursor.rowcount > 0

    def update_session_last_seen(
        self, conn: sqlite3.Connection, session_id: int, last_seen_at: str
    ) -> None:
        conn.execute(
            "UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?",
            (last_seen_at, session_id),
        )

    def list_user_sessions(self, conn: sqlite3.Connection, user_id: int) -> list[AuthSession]:
        rows = conn.execute(
            "SELECT * FROM auth_sessions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_session(r) for r in rows]

    # -------------------------------------------------------------------------
    # Rate Limiting Operations
    # -------------------------------------------------------------------------

    def get_login_attempt(self, conn: sqlite3.Connection, attempt_key: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM auth_login_attempts WHERE attempt_key = ?",
            (attempt_key,),
        ).fetchone()

    def check_login_rate_limits(
        self,
        conn: sqlite3.Connection,
        keys: list[str],
        now: datetime,
    ) -> tuple[bool, int, str | None]:
        """Checks whether any key in keys is currently locked out.

        Returns (is_locked, retry_after_seconds, locked_key).
        """
        max_retry_after = 0
        locked_key: str | None = None

        for key in keys:
            row = conn.execute(
                "SELECT locked_until FROM auth_login_attempts WHERE attempt_key = ?",
                (key,),
            ).fetchone()
            if row and row["locked_until"]:
                try:
                    locked_dt = datetime.fromisoformat(row["locked_until"])
                    if locked_dt.tzinfo is None:
                        locked_dt = locked_dt.replace(tzinfo=timezone.utc)
                    if now < locked_dt:
                        diff = (locked_dt - now).total_seconds()
                        retry_after = max(1, math.ceil(diff))
                        if retry_after > max_retry_after:
                            max_retry_after = retry_after
                            locked_key = key
                except Exception:
                    pass

        if max_retry_after > 0:
            return True, max_retry_after, locked_key
        return False, 0, None

    def record_login_failure_atomic(
        self,
        conn: sqlite3.Connection,
        buckets: list[tuple[str, int, int, int]],
        now: datetime,
    ) -> tuple[str, int, str | None]:
        """Atomically updates failure counts and lockouts for a list of buckets.

        Must be executed within a transaction started with BEGIN IMMEDIATE.
        Returns:
            ("BLOCKED", retry_after_seconds, locked_key) if already locked before this attempt (no increment made).
            ("FAILURE_RECORDED_AND_NOW_LOCKED", retry_after_seconds, locked_key) if this failure triggered a new lock.
            ("FAILURE_RECORDED", 0, None) if failure recorded without triggering lock.
        """
        now_iso = now.isoformat()
        parsed_buckets = []
        max_retry_after = 0
        already_locked_key = None

        # 1-5. Load all buckets, recalculate window expirations, and check current locked_until
        for key, max_attempts, window_seconds, lockout_seconds in buckets:
            row = conn.execute(
                "SELECT failed_count, first_failed_at, last_failed_at, locked_until FROM auth_login_attempts WHERE attempt_key = ?",
                (key,),
            ).fetchone()

            if row is not None and row["locked_until"]:
                try:
                    locked_dt = datetime.fromisoformat(row["locked_until"])
                    if locked_dt.tzinfo is None:
                        locked_dt = locked_dt.replace(tzinfo=timezone.utc)
                    if now < locked_dt:
                        diff = (locked_dt - now).total_seconds()
                        retry_after = max(1, math.ceil(diff))
                        if retry_after > max_retry_after:
                            max_retry_after = retry_after
                            already_locked_key = key
                except Exception:
                    pass

            parsed_buckets.append((key, max_attempts, window_seconds, lockout_seconds, row))

        # 6. If any bucket was ALREADY locked before this attempt:
        # DO NOT increment; return BLOCKED status
        if max_retry_after > 0:
            return "BLOCKED", max_retry_after, already_locked_key

        # 7-8. Otherwise, atomically increment all buckets
        triggered_lock = False
        new_lock_key = None
        new_lock_seconds = 0

        for key, max_attempts, window_seconds, lockout_seconds, row in parsed_buckets:
            if row is None:
                is_locked = max_attempts <= 1
                locked_until = (now + timedelta(seconds=lockout_seconds)).isoformat() if is_locked else None
                if is_locked:
                    triggered_lock = True
                    new_lock_key = key
                    new_lock_seconds = lockout_seconds
                conn.execute(
                    """
                    INSERT INTO auth_login_attempts (attempt_key, failed_count, first_failed_at, last_failed_at, locked_until)
                    VALUES (?, 1, ?, ?, ?)
                    """,
                    (key, now_iso, now_iso, locked_until),
                )
            else:
                try:
                    first_failed_dt = datetime.fromisoformat(row["first_failed_at"])
                    if first_failed_dt.tzinfo is None:
                        first_failed_dt = first_failed_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    first_failed_dt = now

                window_expired = (now - first_failed_dt).total_seconds() > window_seconds

                if window_expired:
                    new_count = 1
                    first_ts = now_iso
                    is_locked = max_attempts <= 1
                    lock_ts = (now + timedelta(seconds=lockout_seconds)).isoformat() if is_locked else None
                    if is_locked:
                        triggered_lock = True
                        new_lock_key = key
                        new_lock_seconds = lockout_seconds
                else:
                    new_count = int(row["failed_count"]) + 1
                    first_ts = str(row["first_failed_at"])
                    if new_count >= max_attempts:
                        lock_ts = (now + timedelta(seconds=lockout_seconds)).isoformat()
                        triggered_lock = True
                        new_lock_key = key
                        new_lock_seconds = lockout_seconds
                    else:
                        lock_ts = None

                conn.execute(
                    """
                    UPDATE auth_login_attempts
                    SET failed_count = ?, first_failed_at = ?, last_failed_at = ?, locked_until = ?
                    WHERE attempt_key = ?
                    """,
                    (new_count, first_ts, now_iso, lock_ts, key),
                )

        if triggered_lock:
            return "FAILURE_RECORDED_AND_NOW_LOCKED", new_lock_seconds, new_lock_key
        return "FAILURE_RECORDED", 0, None

    def reset_user_login_attempts(self, conn: sqlite3.Connection, username: str) -> None:
        conn.execute("DELETE FROM auth_login_attempts WHERE attempt_key = ?", (f"user:{username}",))

    def prune_stale_login_attempts(self, conn: sqlite3.Connection, older_than_iso: str) -> int:
        cursor = conn.execute(
            """
            DELETE FROM auth_login_attempts
            WHERE (locked_until IS NULL OR locked_until < ?) AND last_failed_at < ?
            """,
            (older_than_iso, older_than_iso),
        )
        return cursor.rowcount
