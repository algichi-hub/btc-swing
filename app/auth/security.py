from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import re
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Password policy minimum length for V4 Block 1 (provisional, can be strengthened later)
MIN_PASSWORD_LENGTH: Final[int] = 8
MIN_USERNAME_LENGTH: Final[int] = 3
MAX_USERNAME_LENGTH: Final[int] = 64

_USERNAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]+$")

# Argon2id hasher using recommended OWASP defaults (RFC 9106)
# argon2.PasswordHasher defaults: type=argon2.Type.ID, time_cost=3, memory_cost=65536, parallelism=4
_hasher = PasswordHasher()


def validate_password_policy(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")


def normalize_username(username: str) -> str:
    if not isinstance(username, str):
        raise ValueError("Username must be a string")
    normalized = username.strip()
    if not (MIN_USERNAME_LENGTH <= len(normalized) <= MAX_USERNAME_LENGTH):
        raise ValueError(
            f"Username length must be between {MIN_USERNAME_LENGTH} and {MAX_USERNAME_LENGTH} characters"
        )
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Username may only contain ASCII letters, numbers, hyphens, underscores, and dots"
        )
    return normalized.lower()


def hash_password(password: str) -> str:
    validate_password_policy(password)
    # PasswordHasher generates a unique random salt on every invocation
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not isinstance(password, str) or not isinstance(password_hash, str):
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:
        return False


def generate_session_token() -> str:
    # 32 bytes (256 bits) of cryptographic randomness formatted as urlsafe string
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("Session token must be a non-empty string")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


CSRF_DOMAIN_PREFIX: Final[bytes] = b"btc-swing-trade-csrf-v1:"


def validate_csrf_secret(secret: str) -> bytes:
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError("AUTH_CSRF_SECRET must be a non-empty string")
    s = secret.strip()
    missing_padding = len(s) % 4
    if missing_padding:
        s += "=" * (4 - missing_padding)
    try:
        raw_bytes = base64.urlsafe_b64decode(s)
    except Exception as exc:
        raise ValueError("AUTH_CSRF_SECRET must be valid base64url-encoded data") from exc
    if len(raw_bytes) < 32:
        raise ValueError(
            f"AUTH_CSRF_SECRET must decode to at least 32 bytes of entropy (got {len(raw_bytes)} bytes)"
        )
    return raw_bytes


def derive_csrf_token(session_token_hash: str, secret: str) -> str:
    if not isinstance(session_token_hash, str) or not session_token_hash:
        raise ValueError("session_token_hash must be a non-empty string")
    if not isinstance(secret, str) or not secret:
        raise ValueError("secret must be a non-empty string")
    msg = CSRF_DOMAIN_PREFIX + session_token_hash.encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest().lower()


_DUMMY_ARGON2_HASH: Final[str] = _hasher.hash("btc_swing_trade_dummy_anti_timing_salt_v4")


def verify_dummy_password(password: str) -> bool:
    if not isinstance(password, str):
        return False
    try:
        return _hasher.verify(_DUMMY_ARGON2_HASH, password)
    except Exception:
        return False


def check_needs_rehash(password_hash: str) -> bool:
    if not isinstance(password_hash, str):
        return False
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False
