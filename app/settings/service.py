from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import re
from typing import Any, Mapping

from app.storage.database import connect


class SettingsValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SettingSpec:
    key: str
    value_type: str
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[str, ...] | None = None


SettingValue = int | float | str


DAILY_SWING_CANDLES = "daily_swing_candles"
BACKTEST_CANDLES = "backtest_candles"
LOOKBACK_DAYS = "lookback_days"
PIVOT_LEFT = "pivot_left"
PIVOT_RIGHT = "pivot_right"
MIN_CONFIRMATIONS = "min_confirmations"
CLUSTER_TOLERANCE_PCT = "cluster_tolerance_pct"
SMA20_FILTER_PCT = "sma20_filter_pct"
OPERATIONAL_RANGE_PCT = "operational_range_pct"
MIN_OPERATIONAL_RANGE_PCT = "min_operational_range_pct"
PNL_CHART_DAYS = "pnl_chart_days"
VOLUME_BASELINE_PERIOD = "volume_baseline_period"
VOLUME_CONFIRMATION_THRESHOLD = "volume_confirmation_threshold"
SETTING_SPECS: dict[str, SettingSpec] = {
    DAILY_SWING_CANDLES: SettingSpec(
        key=DAILY_SWING_CANDLES,
        value_type="int",
        minimum=60,
        maximum=1500,
    ),
    BACKTEST_CANDLES: SettingSpec(
        key=BACKTEST_CANDLES,
        value_type="int",
        minimum=120,
        maximum=5000,
    ),
    LOOKBACK_DAYS: SettingSpec(
        key=LOOKBACK_DAYS,
        value_type="int",
        minimum=1,
        maximum=5000,
    ),
    PIVOT_LEFT: SettingSpec(
        key=PIVOT_LEFT,
        value_type="int",
        minimum=1,
        maximum=20,
    ),
    PIVOT_RIGHT: SettingSpec(
        key=PIVOT_RIGHT,
        value_type="int",
        minimum=1,
        maximum=20,
    ),
    MIN_CONFIRMATIONS: SettingSpec(
        key=MIN_CONFIRMATIONS,
        value_type="int",
        minimum=1,
        maximum=20,
    ),
    CLUSTER_TOLERANCE_PCT: SettingSpec(
        key=CLUSTER_TOLERANCE_PCT,
        value_type="float",
        minimum=0.0,
        maximum=100.0,
    ),
    SMA20_FILTER_PCT: SettingSpec(
        key=SMA20_FILTER_PCT,
        value_type="float",
        minimum=0.0,
        maximum=100.0,
    ),
    OPERATIONAL_RANGE_PCT: SettingSpec(
        key=OPERATIONAL_RANGE_PCT,
        value_type="float",
        minimum=0.0,
        maximum=100.0,
    ),
    MIN_OPERATIONAL_RANGE_PCT: SettingSpec(
        key=MIN_OPERATIONAL_RANGE_PCT,
        value_type="float",
        minimum=0.0,
        maximum=100.0,
    ),
    PNL_CHART_DAYS: SettingSpec(
        key=PNL_CHART_DAYS,
        value_type="int",
        minimum=7,
        maximum=90,
    ),
    VOLUME_BASELINE_PERIOD: SettingSpec(
        key=VOLUME_BASELINE_PERIOD,
        value_type="int",
        minimum=5,
        maximum=168,
    ),
    VOLUME_CONFIRMATION_THRESHOLD: SettingSpec(
        key=VOLUME_CONFIRMATION_THRESHOLD,
        value_type="float",
        minimum=0.50,
        maximum=5.00,
    ),
}


class SettingsService:
    def __init__(self, database_path: Path, daily_default: int, backtest_default: int) -> None:
        self.database_path = database_path
        self.defaults = {
            DAILY_SWING_CANDLES: daily_default,
            BACKTEST_CANDLES: backtest_default,
            LOOKBACK_DAYS: 120,
            PIVOT_LEFT: 2,
            PIVOT_RIGHT: 2,
            MIN_CONFIRMATIONS: 2,
            CLUSTER_TOLERANCE_PCT: 2.0,
            SMA20_FILTER_PCT: 9.0,
            OPERATIONAL_RANGE_PCT: 10.0,
            MIN_OPERATIONAL_RANGE_PCT: 0.0,  # 0.0 is a temporary neutral implementation default and is NOT the approved production default for V3.
            PNL_CHART_DAYS: 30,  # 30 is a temporary technical default for PNL_CHART_DAYS and is not the final user-approved production default.
            VOLUME_BASELINE_PERIOD: 20,
            VOLUME_CONFIRMATION_THRESHOLD: 1.05,
        }

    def apply_defaults(self) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        values = self._validate_input(self.defaults)

        with connect(self.database_path) as conn:
            for key, value in values.items():
                conn.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO NOTHING
                    """,
                    (key, self._serialize_value(key, value), timestamp),
                )

    def get(self, key: str) -> SettingValue:
        if key not in SETTING_SPECS:
            raise SettingsValidationError(f"Unknown setting: {key}")

        self.apply_defaults()

        with connect(self.database_path) as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()

        if row is None:
            return self.defaults[key]

        return self._coerce_value(key, row["value"])

    def get_all(self) -> dict[str, SettingValue]:
        self.apply_defaults()
        keys = list(SETTING_SPECS.keys())
        placeholders = ",".join("?" for _ in keys)

        with connect(self.database_path) as conn:
            rows = conn.execute(
                f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
                tuple(keys),
            ).fetchall()

        values = {row["key"]: self._coerce_value(row["key"], row["value"]) for row in rows}

        for key in keys:
            values.setdefault(key, self.defaults[key])

        return values

    def update_many(self, updates: Mapping[str, Any]) -> dict[str, SettingValue]:
        if not updates:
            raise SettingsValidationError("No settings were provided")

        self.apply_defaults()
        normalized = self._validate_input(updates)
        timestamp = datetime.now(timezone.utc).isoformat()

        with connect(self.database_path) as conn:
            for key, value in normalized.items():
                conn.execute(
                    "UPDATE app_settings SET value = ?, updated_at = ? WHERE key = ?",
                    (self._serialize_value(key, value), timestamp, key),
                )

        return self.get_all()

    def _validate_input(self, updates: Mapping[str, Any]) -> dict[str, SettingValue]:
        normalized: dict[str, SettingValue] = {}

        for key, raw_value in updates.items():
            if key not in SETTING_SPECS:
                allowed = ", ".join(sorted(SETTING_SPECS))
                raise SettingsValidationError(f"Unknown setting '{key}'. Allowed: {allowed}")

            value = self._coerce_value(key, raw_value)
            normalized[key] = value

        return normalized

    def _coerce_value(self, key: str, raw_value: Any) -> SettingValue:
        spec = SETTING_SPECS[key]

        if spec.value_type == "int":
            return self._coerce_int(key, raw_value, spec)
        if spec.value_type == "float":
            return self._coerce_float(key, raw_value, spec)
        if spec.value_type == "str":
            return self._coerce_str(key, raw_value, spec)

        raise SettingsValidationError(f"Unsupported setting type for {key}")

    def _coerce_int(self, key: str, raw_value: Any, spec: SettingSpec) -> int:
        if isinstance(raw_value, bool):
            raise SettingsValidationError(f"{key} must be an integer")

        if raw_value is None:
            raise SettingsValidationError(f"{key} must be an integer")

        if isinstance(raw_value, str):
            candidate = raw_value.strip()
            if candidate == "":
                raise SettingsValidationError(f"{key} must be an integer")
            if any(char in candidate.lower() for char in (".", "e")):
                raise SettingsValidationError(f"{key} must be an integer")
        else:
            candidate = raw_value

        if isinstance(candidate, float):
            if not math.isfinite(candidate):
                raise SettingsValidationError(f"{key} must be finite")
            if not candidate.is_integer():
                raise SettingsValidationError(f"{key} must be an integer")

        try:
            value = int(candidate)
        except (TypeError, ValueError) as exc:
            raise SettingsValidationError(f"{key} must be an integer") from exc

        if value < 0:
            raise SettingsValidationError(f"{key} must be non-negative")

        if spec.minimum is not None and value < spec.minimum:
            raise SettingsValidationError(
                f"{key} must be between {spec.minimum} and {spec.maximum}"
            )
        if spec.maximum is not None and value > spec.maximum:
            raise SettingsValidationError(
                f"{key} must be between {spec.minimum} and {spec.maximum}"
            )

        if key == PNL_CHART_DAYS and value not in (7, 30, 90):
            raise SettingsValidationError(f"{key} must be one of: 7, 30, 90")

        return value

    def _coerce_float(self, key: str, raw_value: Any, spec: SettingSpec) -> float:
        if isinstance(raw_value, bool):
            raise SettingsValidationError(f"{key} must be a number")

        if raw_value is None:
            raise SettingsValidationError(f"{key} must be a number")

        if isinstance(raw_value, str):
            candidate = raw_value.strip()
            if candidate == "":
                raise SettingsValidationError(f"{key} must be a number")
        else:
            candidate = raw_value

        try:
            value = float(candidate)
        except (TypeError, ValueError) as exc:
            raise SettingsValidationError(f"{key} must be a number") from exc

        if not math.isfinite(value):
            raise SettingsValidationError(f"{key} must be finite")
        if value < 0:
            raise SettingsValidationError(f"{key} must be non-negative")
        if spec.minimum is not None and value < spec.minimum:
            raise SettingsValidationError(
                f"{key} must be between {spec.minimum} and {spec.maximum}"
            )
        if spec.maximum is not None and value > spec.maximum:
            raise SettingsValidationError(
                f"{key} must be between {spec.minimum} and {spec.maximum}"
            )

        return value

    def _coerce_str(self, key: str, raw_value: Any, spec: SettingSpec) -> str:
        if isinstance(raw_value, bool) or not isinstance(raw_value, str):
            raise SettingsValidationError(f"{key} must be a string")

        candidate = raw_value.strip()
        if candidate == "":
            raise SettingsValidationError(f"{key} must not be empty")

        if key == PNL_RECAP_WEEKDAY:
            candidate_upper = candidate.upper()
            if candidate_upper not in VALID_PNL_RECAP_WEEKDAYS:
                allowed = ", ".join(VALID_PNL_RECAP_WEEKDAYS)
                raise SettingsValidationError(f"{key} must be one of: {allowed}")
            return candidate_upper

        if key == PNL_RECAP_TIME:
            match = re.match(r"^([01]\d|2[0-3]):[0-5]\d$", candidate)
            if not match:
                raise SettingsValidationError(
                    f"{key} must be a valid 24h time in HH:MM format between 00:00 and 23:59"
                )
            return candidate

        if spec.allowed_values and candidate not in spec.allowed_values:
            allowed = ", ".join(spec.allowed_values)
            raise SettingsValidationError(f"{key} must be one of: {allowed}")

        return candidate

    def _serialize_value(self, key: str, value: SettingValue) -> str:
        spec = SETTING_SPECS[key]
        if spec.value_type == "int":
            return str(int(value))
        if spec.value_type == "float":
            return str(float(value))
        return str(value)
