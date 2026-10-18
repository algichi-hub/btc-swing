"""No-op legacy notification adapter for V5 cloud.

The V4 trading engine signature requires a notifier argument. This adapter
has no transport, token, chat ID or networking capability. Never use as an
operational Web Push dispatcher.
"""
from __future__ import annotations

class CloudNotificationDisabled(RuntimeError):
    pass

class NullLegacyNotifier:
    @property
    def configured(self) -> bool:
        return False

    def send_message(self, *_args, **_kwargs) -> None:
        raise CloudNotificationDisabled("Legacy Telegram transport is disabled in V5 cloud")
