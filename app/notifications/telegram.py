from __future__ import annotations

import requests


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramDeliveryError(RuntimeError):
    pass


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout_seconds: float = 15.0) -> None:
        self.token = token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str) -> str | None:
        if not self.configured:
            raise TelegramConfigurationError("Telegram is not fully configured")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TelegramDeliveryError("Telegram request failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError("Telegram response was not valid JSON") from exc

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise TelegramDeliveryError("Telegram API rejected the message")

        result = payload.get("result")
        if not isinstance(result, dict):
            return None

        message_id = result.get("message_id")
        return None if message_id is None else str(message_id)
