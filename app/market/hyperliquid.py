from __future__ import annotations

import time
from typing import Any

import requests

from app.models import Candle

INTERVAL_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


class HyperliquidError(RuntimeError):
    pass


class HyperliquidClient:
    def __init__(self, info_url: str, timeout_seconds: float = 20.0) -> None:
        self.info_url = info_url
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": "btc-swing-engine/2.0",
            }
        )

    def _post(self, payload: dict[str, Any]) -> Any:
        try:
            response = self.session.post(
                self.info_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise HyperliquidError("Timeout consultando Hyperliquid.") from exc
        except requests.RequestException as exc:
            raise HyperliquidError(
                f"Error HTTP consultando Hyperliquid: {exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise HyperliquidError(
                "Respuesta JSON inválida de Hyperliquid."
            ) from exc

        if data is None or data == "":
            raise HyperliquidError("Respuesta vacía de Hyperliquid.")
        if isinstance(data, dict) and data.get("error"):
            raise HyperliquidError(str(data["error"]))
        return data

    def get_mid(self, coin: str) -> float:
        mids = self._post({"type": "allMids"})
        if not isinstance(mids, dict) or coin not in mids:
            raise HyperliquidError(
                f"No se encontró {coin!r} en la respuesta allMids."
            )
        return float(mids[coin])

    def get_candles(self, coin: str, interval: str, count: int) -> list[Candle]:
        if interval not in INTERVAL_MS:
            raise ValueError(f"Intervalo no soportado: {interval}")

        end_time = int(time.time() * 1000)
        start_time = end_time - (count + 5) * INTERVAL_MS[interval]
        rows = self._post(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": coin,
                    "interval": interval,
                    "startTime": start_time,
                    "endTime": end_time,
                },
            }
        )
        if not isinstance(rows, list):
            raise HyperliquidError(
                f"Respuesta de velas inesperada: {type(rows).__name__}"
            )

        candles_by_time: dict[int, Candle] = {}
        for row in rows:
            try:
                candle = Candle(
                    open_time_ms=int(row["t"]),
                    close_time_ms=int(row["T"]),
                    open=float(row["o"]),
                    high=float(row["h"]),
                    low=float(row["l"]),
                    close=float(row["c"]),
                    volume=float(row["v"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise HyperliquidError(f"Vela inválida recibida: {row!r}") from exc
            candles_by_time[candle.open_time_ms] = candle

        ordered = [candles_by_time[key] for key in sorted(candles_by_time)]
        return ordered[-count:]


def closed_candles(candles: list[Candle], safety_seconds: int = 15) -> list[Candle]:
    cutoff = int(time.time() * 1000) - safety_seconds * 1000
    return [candle for candle in candles if candle.close_time_ms <= cutoff]
