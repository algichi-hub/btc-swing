"""F6 release guardrails for cloud roles.

This module has no network side effects and does not alter the frozen V4
trading algorithm. Fail closed on legacy integrations or real-money trading.
"""
from __future__ import annotations
import os

CLOUD_ROLES=frozenset({"worker","push_dispatcher","api"})
TRUE=frozenset({"1","true","yes","on"})

def enforce_cloud_isolation(*, role: str | None = None) -> None:
    role=(role if role is not None else os.getenv("BTC_PROCESS_ROLE","")).strip()
    if role not in CLOUD_ROLES:
        return
    if os.getenv("BTC_DB_BACKEND") != "postgres":
        raise RuntimeError("F6 requires PostgreSQL for cloud roles")
    if os.getenv("BTC_LIVE_TRADING","").lower() in TRUE:
        raise RuntimeError("F6 prohibits real-money orders")
    if os.getenv("TELEGRAM_ENABLED","").lower() in TRUE:
        raise RuntimeError("F6 prohibits Telegram on cloud services")
    if any(os.getenv(k) for k in ("TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID")):
        raise RuntimeError("F6 prohibits Telegram secrets on cloud services")
    if os.getenv("PUSH_DELAYED_TEST_ENABLED","").lower() in TRUE:
        raise RuntimeError("F6 retired temporary delayed Push endpoint")
    if role=="push_dispatcher":
        if os.getenv("PUSH_DISPATCHER_REAL_SEND","").lower() in TRUE and os.getenv("PUSH_REAL_EVENTS_ENABLED")!="true":
            raise RuntimeError("F6 dispatcher real-send requires an explicit events gate")
        if os.getenv("PUSH_DISPATCHER_REAL_SEND","").lower() in TRUE and not all(
                os.getenv(k) for k in ("PUSH_VAPID_PRIVATE_KEY","PUSH_VAPID_SUBJECT","PUSH_SUBSCRIPTION_ENCRYPTION_KEY")):
            raise RuntimeError("F6 dispatcher VAPID and encryption keys required")

def assert_release_eligible(flags: dict[str,bool]) -> None:
    """Refuse promotion unless all signed evidence-backed release conditions pass."""
    required=("g3_midwrite_recovery","g4_authenticated_rbac","g4_logout_csrf",
              "g5_provider_retries","g5_android_resubscribe",
              "telegram_removed","full_regression","rollback_verified")
    missing=[name for name in required if flags.get(name) is not True]
    if missing:
        raise RuntimeError("F6 production NO-GO: "+", ".join(missing))
