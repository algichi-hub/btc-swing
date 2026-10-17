from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

DEFAULT_CSRF_SECRET = "dGVzdF9jc3JmX3NlY3JldF8zMl9ieXRlc19sb25nX2VudHJvcHlfa2V5XzEyMzQ1Nzg="

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _int_with_aliases(name: str, default: int, aliases: tuple[str, ...]) -> int:
    raw = os.getenv(name)
    if raw is None:
        for alias in aliases:
            alias_raw = os.getenv(alias)
            if alias_raw is not None:
                raw = alias_raw
                break
    return int(raw if raw is not None else str(default))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: str) -> Path:
    raw = Path(os.getenv(name, default))
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


def _tuple_str(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return tuple(items) if items else default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", os.getenv("HOST", "127.0.0.1"))
    app_port: int = _int_with_aliases("APP_PORT", 8005, ("PORT",))
    refresh_interval_seconds: int = _int("REFRESH_INTERVAL_SECONDS", 300)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    timezone: str = os.getenv("TIMEZONE", "Europe/Berlin")
    daily_swing_candles_default: int = _int("DAILY_SWING_CANDLES_DEFAULT", 120)
    backtest_candles_default: int = _int("BACKTEST_CANDLES_DEFAULT", 730)

    info_url: str = os.getenv("HYPERLIQUID_INFO_URL", "https://api.hyperliquid.xyz/info")
    coin: str = os.getenv("COIN", "BTC").upper()
    daily_candles: int = _int("DAILY_CANDLES", 730)
    hourly_candles: int = _int("HOURLY_CANDLES", 8760)
    refresh_at_minute: int = _int("REFRESH_AT_MINUTE", 3)

    swing_left: int = _int("SWING_LEFT", 2)
    swing_right: int = _int("SWING_RIGHT", 2)
    swing_lookahead: int = _int("SWING_LOOKAHEAD", 10)
    atr_period_daily: int = _int("ATR_PERIOD_DAILY", 14)
    atr_period_hourly: int = _int("ATR_PERIOD_HOURLY", 14)
    min_swing_move_pct: float = _float("MIN_SWING_MOVE_PCT", 0.03)
    min_swing_move_atr: float = _float("MIN_SWING_MOVE_ATR", 1.0)
    swing_sma_period: int = _int("SWING_SMA_PERIOD", 20)
    swing_sma_max_distance_pct: float = _float("SWING_SMA_MAX_DISTANCE_PCT", 0.09)
    swing_cluster_tolerance_pct: float = _float("SWING_CLUSTER_TOLERANCE_PCT", 0.025)
    cluster_atr_multiple: float = _float("CLUSTER_ATR_MULTIPLE", 0.35)
    zone_padding_atr: float = _float("ZONE_PADDING_ATR", 0.12)
    min_range_atr_multiple: float = _float("MIN_RANGE_ATR_MULTIPLE", 1.2)
    min_range_pct: float = _float("MIN_RANGE_PCT", 0.04)
    stop_buffer_atr_1h: float = _float("STOP_BUFFER_ATR_1H", 0.35)

    volume_baseline_period: int = _int("VOLUME_BASELINE_PERIOD", 20)
    volume_confirmation_threshold: float = _float("VOLUME_CONFIRMATION_THRESHOLD", 1.05)
    rsi_period: int = _int("RSI_PERIOD", 14)
    stoch_rsi_period: int = _int("STOCH_RSI_PERIOD", 14)
    stoch_k: int = _int("STOCH_K", 3)
    stoch_d: int = _int("STOCH_D", 3)

    high_min_weighted_rr: float = _float("HIGH_MIN_WEIGHTED_RR", 1.80)
    high_min_expectancy_r: float = _float("HIGH_MIN_EXPECTANCY_R", 0.25)
    high_min_samples: int = _int("HIGH_MIN_SAMPLES", 30)
    very_high_min_weighted_rr: float = _float("VERY_HIGH_MIN_WEIGHTED_RR", 2.20)
    very_high_min_expectancy_r: float = _float("VERY_HIGH_MIN_EXPECTANCY_R", 0.50)
    very_high_min_samples: int = _int("VERY_HIGH_MIN_SAMPLES", 50)

    tp1_allocation: float = _float("TP1_ALLOCATION", 0.30)
    tp2_allocation: float = _float("TP2_ALLOCATION", 0.30)
    tp3_allocation: float = _float("TP3_ALLOCATION", 0.40)
    min_margin_usd: float = _float("MIN_MARGIN_USD", 50)
    base_margin_usd: float = _float("BASE_MARGIN_USD", 100)
    max_margin_usd: float = _float("MAX_MARGIN_USD", 200)
    min_leverage: int = _int("MIN_LEVERAGE", 5)
    max_leverage: int = _int("MAX_LEVERAGE", 25)
    max_margin_loss_pct: float = _float("MAX_MARGIN_LOSS_PCT", 0.30)
    max_trade_loss_usd: float = _float("MAX_TRADE_LOSS_USD", 40)

    database_path: Path = _path("DATABASE_PATH", "data/btc_swing_trade.db")
    auth_session_ttl_hours: int = _int("AUTH_SESSION_TTL_HOURS", 168)
    auth_session_touch_interval_seconds: int = _int("AUTH_SESSION_TOUCH_INTERVAL_SECONDS", 300)
    auth_cookie_secure: bool = _bool(
        "AUTH_COOKIE_SECURE",
        default=(os.getenv("APP_ENV", "development").strip().lower() == "production"),
    )
    auth_csrf_secret: str = os.getenv(
        "AUTH_CSRF_SECRET",
        DEFAULT_CSRF_SECRET,
    )
    auth_allowed_origins: tuple[str, ...] = _tuple_str(
        "AUTH_ALLOWED_ORIGINS",
        ("http://127.0.0.1:8008", "http://localhost:8008", "http://testserver"),
    ) + _tuple_str("AUTH_EXTRA_ALLOWED_ORIGINS", ())
    auth_allowed_hosts: tuple[str, ...] = _tuple_str(
        "AUTH_ALLOWED_HOSTS",
        ("localhost", "127.0.0.1", "testserver"),
    )
    auth_rate_limit_user_max: int = _int("AUTH_RATE_LIMIT_USER_MAX", 5)
    auth_rate_limit_ip_max: int = _int("AUTH_RATE_LIMIT_IP_MAX", 20)
    auth_rate_limit_global_max: int = _int("AUTH_RATE_LIMIT_GLOBAL_MAX", 100)
    auth_rate_limit_window_seconds: int = _int("AUTH_RATE_LIMIT_WINDOW_SECONDS", 900)
    auth_rate_limit_lockout_seconds: int = _int("AUTH_RATE_LIMIT_LOCKOUT_SECONDS", 900)

    telegram_enabled: bool = _bool("TELEGRAM_ENABLED", False)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_timezone: str = os.getenv("TELEGRAM_TIMEZONE", "Europe/Madrid")
    telegram_daily_report_hour: int = _int("TELEGRAM_DAILY_REPORT_HOUR", 7)
    telegram_daily_report_minute: int = _int("TELEGRAM_DAILY_REPORT_MINUTE", 0)

    def validate_runtime(self) -> None:
        if self.app_env.strip().lower() == "production":
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE cannot be false when APP_ENV is production")
            raw_secret = (self.auth_csrf_secret or os.getenv("AUTH_CSRF_SECRET", "")).strip()
            if not raw_secret or raw_secret == DEFAULT_CSRF_SECRET:
                raise ValueError("AUTH_CSRF_SECRET must be explicitly configured with a unique value in production")
            from app.auth.security import validate_csrf_secret
            try:
                validate_csrf_secret(raw_secret)
            except Exception as exc:
                raise ValueError(f"AUTH_CSRF_SECRET is invalid in production: {exc}") from exc
            if not self.auth_allowed_origins or "*" in self.auth_allowed_origins:
                raise ValueError("AUTH_ALLOWED_ORIGINS cannot be empty or contain '*' in production")
            if not self.auth_allowed_hosts or "*" in self.auth_allowed_hosts:
                raise ValueError("AUTH_ALLOWED_HOSTS cannot be empty or contain '*' in production")

        if self.auth_session_ttl_hours <= 0:
            raise ValueError("AUTH_SESSION_TTL_HOURS must be greater than zero")
        if self.auth_session_touch_interval_seconds <= 0:
            raise ValueError("AUTH_SESSION_TOUCH_INTERVAL_SECONDS must be greater than zero")
        if self.auth_rate_limit_user_max <= 0:
            raise ValueError("AUTH_RATE_LIMIT_USER_MAX must be greater than zero")
        if self.auth_rate_limit_ip_max <= 0:
            raise ValueError("AUTH_RATE_LIMIT_IP_MAX must be greater than zero")
        if self.auth_rate_limit_global_max <= 0:
            raise ValueError("AUTH_RATE_LIMIT_GLOBAL_MAX must be greater than zero")
        if self.auth_rate_limit_window_seconds <= 0:
            raise ValueError("AUTH_RATE_LIMIT_WINDOW_SECONDS must be greater than zero")
        if self.auth_rate_limit_lockout_seconds <= 0:
            raise ValueError("AUTH_RATE_LIMIT_LOCKOUT_SECONDS must be greater than zero")

        if abs((self.tp1_allocation + self.tp2_allocation + self.tp3_allocation) - 1.0) > 1e-9:
            raise ValueError("TP allocations must sum to 1.0")
        if self.telegram_enabled and (not self.telegram_bot_token or not self.telegram_chat_id):
            raise ValueError("Telegram is enabled but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are missing")
        try:
            ZoneInfo(self.telegram_timezone)
        except Exception as exc:
            raise ValueError("TELEGRAM_TIMEZONE is not a valid IANA timezone") from exc
        if not 0 <= self.refresh_at_minute <= 59:
            raise ValueError("REFRESH_AT_MINUTE must be between 0 and 59")
        if self.refresh_interval_seconds <= 0:
            raise ValueError("REFRESH_INTERVAL_SECONDS must be greater than zero")
        if self.daily_swing_candles_default <= 0:
            raise ValueError("DAILY_SWING_CANDLES_DEFAULT must be greater than zero")
        if self.backtest_candles_default <= 0:
            raise ValueError("BACKTEST_CANDLES_DEFAULT must be greater than zero")
        if self.swing_sma_period < 2:
            raise ValueError("SWING_SMA_PERIOD must be at least 2")
        if self.swing_sma_max_distance_pct <= 0:
            raise ValueError("SWING_SMA_MAX_DISTANCE_PCT must be greater than zero")
        if self.swing_cluster_tolerance_pct <= 0 or self.swing_cluster_tolerance_pct > 0.25:
            raise ValueError("SWING_CLUSTER_TOLERANCE_PCT must be greater than zero and <= 0.25")
        if not (5 <= self.volume_baseline_period <= 168):
            raise ValueError("VOLUME_BASELINE_PERIOD must be between 5 and 168")
        if not (0.50 <= self.volume_confirmation_threshold <= 5.00):
            raise ValueError("VOLUME_CONFIRMATION_THRESHOLD must be between 0.50 and 5.00")


settings = Settings()
ALGORITHM_VERSION = "V2.1-beta"
