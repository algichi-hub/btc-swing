from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import Settings
from app.market.hyperliquid import HyperliquidClient, closed_candles
from app.models import Candle
from app.notifications.telegram import TelegramDeliveryError, TelegramNotifier
from app.settings.service import (
    PNL_RECAP_TIME,
    PNL_RECAP_WEEKDAY,
    VALID_PNL_RECAP_WEEKDAYS,
    SettingsService,
)
from app.storage.trade_repository import TradeRepository

RUNTIME_TRADE_WINDOW_OPEN_KEY = "runtime.trade_window_open"
TRACKING_INTERVAL = "5m"
TRACKING_CANDLES = 5000
RUNTIME_LAST_MARKET_CYCLE_AT_KEY = "runtime.last_market_cycle_at"
RUNTIME_LAST_CYCLE_SUCCESS_KEY = "runtime.last_cycle_success"
RUNTIME_LAST_CYCLE_ERROR_KEY = "runtime.last_cycle_error"
RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY = "runtime.pnl_recap_schedule_effective_at"


def iso_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def ms_from_iso(timestamp: str) -> int:
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def calculate_fraction_pnl_usd(
    *,
    side: str,
    entry: float,
    exit_price: float,
    notional_usd: float,
    fraction_closed: float,
) -> float:
    notional_fraction = notional_usd * fraction_closed
    if side.upper() == "LONG":
        return notional_fraction * ((exit_price - entry) / entry)
    return notional_fraction * ((entry - exit_price) / entry)


def calculate_fraction_pnl_r(
    *,
    side: str,
    entry: float,
    stop_loss: float,
    exit_price: float,
    notional_usd: float,
    fraction_closed: float,
) -> float:
    risk_usd = notional_usd * abs(entry - stop_loss) / entry
    if risk_usd <= 0:
        return 0.0

    pnl_usd = calculate_fraction_pnl_usd(
        side=side,
        entry=entry,
        exit_price=exit_price,
        notional_usd=notional_usd,
        fraction_closed=fraction_closed,
    )
    return pnl_usd / risk_usd


def compute_daily_summary_window(
    now_utc: datetime,
    timezone_name: str,
    *,
    report_hour: int,
    report_minute: int,
) -> tuple[datetime, datetime, datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    now_local = now_utc.astimezone(tz)

    anchor_today = now_local.replace(hour=report_hour, minute=report_minute, second=0, microsecond=0)
    if now_local >= anchor_today:
        period_end_local = anchor_today
    else:
        period_end_local = anchor_today - timedelta(days=1)

    period_start_local = period_end_local - timedelta(days=1)
    period_start_utc = period_start_local.astimezone(timezone.utc)
    period_end_utc = period_end_local.astimezone(timezone.utc)

    return period_start_utc, period_end_utc, period_start_local, period_end_local


def compute_pnl_recap_window(
    now_utc: datetime,
    timezone_name: str,
    *,
    target_weekday: str,
    report_hour: int,
    report_minute: int,
) -> tuple[datetime, datetime, datetime, datetime]:
    target_weekday_upper = target_weekday.upper()
    if target_weekday_upper not in VALID_PNL_RECAP_WEEKDAYS:
        raise ValueError(f"Invalid weekday: {target_weekday}")

    target_weekday_idx = VALID_PNL_RECAP_WEEKDAYS.index(target_weekday_upper)
    tz = ZoneInfo(timezone_name)
    now_local = now_utc.astimezone(tz)

    anchor_today = now_local.replace(hour=report_hour, minute=report_minute, second=0, microsecond=0)
    days_back = (now_local.weekday() - target_weekday_idx) % 7

    if days_back == 0:
        if now_local >= anchor_today:
            period_end_local = anchor_today
        else:
            period_end_local = anchor_today - timedelta(days=7)
    else:
        target_date = now_local.date() - timedelta(days=days_back)
        period_end_local = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            report_hour,
            report_minute,
            0,
            0,
            tzinfo=tz,
        )

    period_start_local = period_end_local - timedelta(days=7)
    period_start_utc = period_start_local.astimezone(timezone.utc)
    period_end_utc = period_end_local.astimezone(timezone.utc)

    return period_start_utc, period_end_utc, period_start_local, period_end_local


def format_money(amount: float, *, signed: bool = True) -> str:
    prefix = "+" if signed and amount > 0 else ""
    return f"{prefix}${amount:,.2f}"


class TradingAutomationEngine:
    """Runs autonomous market cycles, paper-trade tracking and telegram summaries."""

    def __init__(
        self,
        *,
        settings: Settings,
        repository: TradeRepository,
        telegram_notifier: TelegramNotifier,
        dashboard_provider: Callable[[], dict[str, Any]],
        market_client_factory: Callable[[], HyperliquidClient] | None = None,
        settings_service: SettingsService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.telegram_notifier = telegram_notifier
        self.dashboard_provider = dashboard_provider
        self.market_client_factory = market_client_factory or (lambda: HyperliquidClient(settings.info_url))
        self.settings_service = settings_service
        self.logger = logger or logging.getLogger(__name__)

    def bootstrap(self) -> None:
        try:
            payload = self.dashboard_provider()
        except Exception:
            self.logger.exception("Initial market bootstrap failed")
            return

        current_open = bool(payload.get("trade_window_open"))
        if self.repository.get_runtime_bool(RUNTIME_TRADE_WINDOW_OPEN_KEY) is None:
            self.repository.set_runtime_bool(RUNTIME_TRADE_WINDOW_OPEN_KEY, current_open)

        try:
            self.retry_pending_trade_alerts()
        except Exception:
            self.logger.exception("Initial pending trade alerts retry failed")

        try:
            self.track_open_trades()
        except Exception:
            self.logger.exception("Initial open-trade tracking failed")

    def run_market_cycle(self) -> None:
        started_at = datetime.now(timezone.utc)
        success = False
        cycle_error = ""

        try:
            try:
                self.ensure_pending_pnl_recap()
            except Exception:
                self.logger.exception("Market cycle pending pnl recap check failed")

            try:
                self.retry_pending_trade_alerts()
            except Exception:
                self.logger.exception("Market cycle pending trade alerts retry failed")

            payload = self.dashboard_provider()
            try:
                self.repository.record_engine_snapshot(payload)
            except Exception:
                self.logger.exception("Failed to record periodic engine snapshot")

            current_open = bool(payload.get("trade_window_open"))

            previous_open = self.repository.get_runtime_bool(RUNTIME_TRADE_WINDOW_OPEN_KEY)
            if previous_open is None:
                self.repository.set_runtime_bool(RUNTIME_TRADE_WINDOW_OPEN_KEY, current_open)
                previous_open = current_open

            should_open = (not previous_open) and current_open

            # Unconditionally record current technical state before attempting downstream alert
            self.repository.set_runtime_bool(RUNTIME_TRADE_WINDOW_OPEN_KEY, current_open)

            if should_open:
                self._handle_window_open(payload)

            self.track_open_trades()
            success = True
        except Exception as exc:
            cycle_error = exc.__class__.__name__
            self.logger.exception("Market cycle execution failed")
        finally:
            completed_at = datetime.now(timezone.utc)
            completed_at_iso = completed_at.isoformat()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            self.repository.set_runtime_state(RUNTIME_LAST_MARKET_CYCLE_AT_KEY, completed_at_iso)
            self.repository.set_runtime_bool(RUNTIME_LAST_CYCLE_SUCCESS_KEY, success)
            self.repository.set_runtime_state(RUNTIME_LAST_CYCLE_ERROR_KEY, cycle_error)

            self.logger.info(
                "Market cycle completed | timestamp=%s | duration_ms=%d | success=%s | error=%s",
                completed_at_iso,
                duration_ms,
                success,
                cycle_error or "none",
            )

    def run_daily_summary(self, now: datetime | None = None) -> None:
        if not self.settings.telegram_enabled or not self.telegram_notifier.configured:
            return

        now_utc = now or datetime.now(timezone.utc)
        period_start_utc, period_end_utc, period_start_local, period_end_local = compute_daily_summary_window(
            now_utc,
            self.settings.telegram_timezone,
            report_hour=self.settings.telegram_daily_report_hour,
            report_minute=self.settings.telegram_daily_report_minute,
        )

        event_key = f"DAILY_SUMMARY:{period_end_local.date().isoformat()}"
        if self.repository.has_successful_telegram_event(event_key):
            return

        period_start_iso = period_start_utc.isoformat()
        period_end_iso = period_end_utc.isoformat()

        signals = self.repository.count_signals_in_period(period_start_iso, period_end_iso)
        closed_trades = self.repository.count_closed_trades_in_period(period_start_iso, period_end_iso)
        open_trades = self.repository.count_open_trades()
        tp1_hits = self.repository.count_trade_events_in_period("TP1", period_start_iso, period_end_iso)
        tp2_hits = self.repository.count_trade_events_in_period("TP2", period_start_iso, period_end_iso)
        tp3_hits = self.repository.count_trade_events_in_period("TP3", period_start_iso, period_end_iso)
        sl_hits = self.repository.count_trade_events_in_period("SL", period_start_iso, period_end_iso)
        realized_pnl = self.repository.sum_realized_pnl_in_period(period_start_iso, period_end_iso)
        average_rr = self.repository.average_weighted_rr_in_period(period_start_iso, period_end_iso)
        open_pnl = self._compute_open_pnl()
        total_marked = realized_pnl + open_pnl

        period_line = f"{period_start_local.strftime('%d/%m %H:%M')} \u2192 {period_end_local.strftime('%d/%m %H:%M')}"

        if signals == 0 and closed_trades == 0 and tp1_hits == 0 and tp2_hits == 0 and tp3_hits == 0 and sl_hits == 0:
            message = (
                "\U0001F4CA BTC SWING \u00b7 RESUMEN 24H\n\n"
                "Periodo:\n"
                f"{period_line}\n\n"
                "Sin nuevas se\u00f1ales.\n\n"
                f"Trades abiertos: {open_trades}\n"
                f"PnL realizado: {format_money(0.0, signed=False)}\n"
                f"PnL abierto: {format_money(0.0, signed=False)}\n"
                f"PnL total marcado: {format_money(0.0, signed=False)}"
            )
        else:
            rr_text = "N/A" if average_rr is None else f"{average_rr:.2f}"
            message = (
                "\U0001F4CA BTC SWING \u00b7 RESUMEN 24H\n\n"
                "Periodo:\n"
                f"{period_line}\n\n"
                f"Se\u00f1ales: {signals}\n"
                f"Trades cerrados: {closed_trades}\n"
                f"Trades abiertos: {open_trades}\n\n"
                f"TP1 alcanzados: {tp1_hits}\n"
                f"TP2 alcanzados: {tp2_hits}\n"
                f"TP3 alcanzados: {tp3_hits}\n"
                f"Stops: {sl_hits}\n\n"
                f"PnL realizado: {format_money(realized_pnl)}\n"
                f"PnL abierto: {format_money(open_pnl)}\n"
                f"PnL total marcado: {format_money(total_marked)}\n\n"
                f"RR medio: {rr_text}"
            )

        try:
            message_id = self.telegram_notifier.send_message(message)
            self.repository.record_telegram_event(
                event_type="DAILY_SUMMARY",
                event_key=event_key,
                success=True,
                telegram_message_id=message_id,
            )
        except Exception as exc:
            self.logger.warning("Daily summary delivery failed: %s", exc)
            self.repository.record_telegram_event(
                event_type="DAILY_SUMMARY",
                event_key=event_key,
                success=False,
                error_message=exc.__class__.__name__,
            )

    def get_recap_settings(self) -> tuple[str, int, int]:
        weekday = "SUNDAY"
        hour = 5
        minute = 0
        if self.settings_service is not None:
            try:
                all_s = self.settings_service.get_all()
                weekday = str(all_s.get(PNL_RECAP_WEEKDAY, "SUNDAY"))
                time_str = str(all_s.get(PNL_RECAP_TIME, "05:00"))
                parts = time_str.split(":")
                hour = int(parts[0])
                minute = int(parts[1])
            except Exception:
                pass
        return weekday, hour, minute

    def ensure_pending_pnl_recap(self, now: datetime | None = None) -> None:
        now_utc = now or datetime.now(timezone.utc)

        # 1. Check or initialize effective_at marker
        effective_at_str = self.repository.get_runtime_state(RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY)
        if effective_at_str is None:
            # Fresh install / initial start: set effective_at to now_utc and do NOT perform retrospective catch-up
            self.repository.set_runtime_state(
                RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY,
                now_utc.isoformat(),
            )
            return

        try:
            effective_at = datetime.fromisoformat(effective_at_str)
            if effective_at.tzinfo is None:
                effective_at = effective_at.replace(tzinfo=timezone.utc)
        except Exception:
            self.repository.set_runtime_state(
                RUNTIME_PNL_RECAP_SCHEDULE_EFFECTIVE_AT_KEY,
                now_utc.isoformat(),
            )
            return

        if not self.settings.telegram_enabled or not self.telegram_notifier.configured:
            return

        weekday, report_hour, report_minute = self.get_recap_settings()

        period_start_utc, period_end_utc, period_start_local, period_end_local = compute_pnl_recap_window(
            now_utc,
            self.settings.telegram_timezone,
            target_weekday=weekday,
            report_hour=report_hour,
            report_minute=report_minute,
        )

        if period_end_utc <= effective_at or period_end_utc > now_utc:
            return

        event_key = f"PNL_RECAP:{period_end_utc.isoformat()}"
        if self.repository.has_successful_telegram_event(event_key):
            return

        self._send_pnl_recap_window(
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            period_start_local=period_start_local,
            period_end_local=period_end_local,
            event_key=event_key,
        )

    def run_pnl_recap(self, now: datetime | None = None) -> None:
        self.ensure_pending_pnl_recap(now=now)

    def recover_missed_pnl_recap(self) -> None:
        self.ensure_pending_pnl_recap()

    def _send_pnl_recap_window(
        self,
        *,
        period_start_utc: datetime,
        period_end_utc: datetime,
        period_start_local: datetime,
        period_end_local: datetime,
        event_key: str,
    ) -> None:
        period_start_iso = period_start_utc.isoformat()
        period_end_iso = period_end_utc.isoformat()

        signals = self.repository.count_signals_in_period(period_start_iso, period_end_iso)
        closed_trades = self.repository.count_closed_trades_in_period(period_start_iso, period_end_iso)
        open_trades = self.repository.count_open_trades()
        tp1_hits = self.repository.count_trade_events_in_period("TP1", period_start_iso, period_end_iso)
        tp2_hits = self.repository.count_trade_events_in_period("TP2", period_start_iso, period_end_iso)
        tp3_hits = self.repository.count_trade_events_in_period("TP3", period_start_iso, period_end_iso)
        sl_hits = self.repository.count_trade_events_in_period("SL", period_start_iso, period_end_iso)
        realized_pnl = self.repository.sum_realized_pnl_in_period(period_start_iso, period_end_iso)
        average_rr = self.repository.average_weighted_rr_in_period(period_start_iso, period_end_iso)
        open_pnl = self._compute_open_pnl()
        total_marked = realized_pnl + open_pnl

        period_line = f"{period_start_local.strftime('%d/%m %H:%M')} → {period_end_local.strftime('%d/%m %H:%M')}"

        if signals == 0 and closed_trades == 0 and tp1_hits == 0 and tp2_hits == 0 and tp3_hits == 0 and sl_hits == 0:
            message = (
                "📊 BTC SWING · RECAP SEMANAL\n\n"
                "Periodo:\n"
                f"{period_line}\n\n"
                "Sin nuevas señales.\n\n"
                f"Trades abiertos: {open_trades}\n"
                f"PnL realizado: {format_money(0.0, signed=False)}\n"
                f"PnL abierto: {format_money(0.0, signed=False)}\n"
                f"PnL total marcado: {format_money(0.0, signed=False)}"
            )
        else:
            rr_text = "N/A" if average_rr is None else f"{average_rr:.2f}"
            message = (
                "📊 BTC SWING · RECAP SEMANAL\n\n"
                "Periodo:\n"
                f"{period_line}\n\n"
                f"Señales: {signals}\n"
                f"Trades cerrados: {closed_trades}\n"
                f"Trades abiertos: {open_trades}\n\n"
                f"TP1 alcanzados: {tp1_hits}\n"
                f"TP2 alcanzados: {tp2_hits}\n"
                f"TP3 alcanzados: {tp3_hits}\n"
                f"Stops: {sl_hits}\n\n"
                f"PnL realizado: {format_money(realized_pnl)}\n"
                f"PnL abierto: {format_money(open_pnl)}\n"
                f"PnL total marcado: {format_money(total_marked)}\n\n"
                f"RR medio: {rr_text}"
            )

        try:
            message_id = self.telegram_notifier.send_message(message)
            self.repository.record_telegram_event(
                event_type="PNL_RECAP",
                event_key=event_key,
                success=True,
                telegram_message_id=message_id,
            )
        except Exception as exc:
            self.logger.warning("PnL recap delivery failed: %s", exc)
            self.repository.record_telegram_event(
                event_type="PNL_RECAP",
                event_key=event_key,
                success=False,
                error_message=exc.__class__.__name__,
            )

    def track_open_trades(self) -> None:
        open_trades = self.repository.list_open_trades()
        if not open_trades:
            return

        client = self.market_client_factory()
        tracking_candles = closed_candles(
            client.get_candles(self.settings.coin, TRACKING_INTERVAL, TRACKING_CANDLES)
        )
        if not tracking_candles:
            return

        for trade in open_trades:
            self._track_single_trade(trade, tracking_candles)

    def _track_single_trade(self, trade: dict[str, Any], candles: list[Candle]) -> None:
        signal_id = int(trade["id"])
        last_processed = trade.get("last_processed_candle_close_ms")

        if last_processed is None:
            created_at_ms = ms_from_iso(str(trade["created_at"]))
            relevant = [candle for candle in candles if candle.close_time_ms >= created_at_ms]
        else:
            relevant = [candle for candle in candles if candle.close_time_ms > int(last_processed)]

        if not relevant:
            return

        runtime_trade = dict(trade)
        last_processed_ms: int | None = None
        for candle in relevant:
            if str(runtime_trade.get("status")) == "CLOSED":
                break
            self._process_trade_candle(runtime_trade, candle)
            last_processed_ms = candle.close_time_ms

        if last_processed_ms is not None:
            self.repository.mark_last_processed_candle(signal_id, last_processed_ms)

    def _process_trade_candle(self, trade: dict[str, Any], candle: Candle) -> None:
        side = str(trade["side"]).upper()
        entry = float(trade["entry_reference"])
        stop_loss = float(trade["stop_loss"])
        notional = float(trade["notional_usd"])
        event_at = iso_from_ms(candle.close_time_ms)

        remaining = float(trade.get("remaining_fraction") or 0.0)
        if remaining <= 1e-9:
            return

        pending_targets = self._pending_targets(trade)
        sl_touched = self._sl_touched(side, candle, stop_loss)

        if sl_touched:
            # Conservative rule: when SL and TP are both touched in the same candle,
            # assume SL happened first and close remaining size at SL.
            self._record_exit(
                trade=trade,
                event_type="SL",
                exit_price=stop_loss,
                fraction_closed=remaining,
                event_at=event_at,
                entry=entry,
                stop_loss=stop_loss,
                notional=notional,
                close_trade=True,
            )
            return

        for event_type, level, allocation, hit_field in pending_targets:
            if not self._tp_touched(side, candle, float(level)):
                continue

            current_remaining = float(trade.get("remaining_fraction") or 0.0)
            if current_remaining <= 1e-9:
                break

            fraction_closed = min(float(allocation), current_remaining)
            close_trade = (current_remaining - fraction_closed) <= 1e-9
            recorded = self._record_exit(
                trade=trade,
                event_type=event_type,
                exit_price=float(level),
                fraction_closed=fraction_closed,
                event_at=event_at,
                entry=entry,
                stop_loss=stop_loss,
                notional=notional,
                close_trade=close_trade,
            )
            if recorded:
                trade[hit_field] = event_at

    def _record_exit(
        self,
        *,
        trade: dict[str, Any],
        event_type: str,
        exit_price: float,
        fraction_closed: float,
        event_at: str,
        entry: float,
        stop_loss: float,
        notional: float,
        close_trade: bool,
    ) -> bool:
        side = str(trade["side"])
        pnl_usd = calculate_fraction_pnl_usd(
            side=side,
            entry=entry,
            exit_price=exit_price,
            notional_usd=notional,
            fraction_closed=fraction_closed,
        )
        pnl_r = calculate_fraction_pnl_r(
            side=side,
            entry=entry,
            stop_loss=stop_loss,
            exit_price=exit_price,
            notional_usd=notional,
            fraction_closed=fraction_closed,
        )

        recorded = self.repository.record_exit_event(
            signal_id=int(trade["id"]),
            event_type=event_type,
            event_at=event_at,
            price=float(exit_price),
            fraction_closed=float(fraction_closed),
            pnl_usd=float(pnl_usd),
            pnl_r=float(pnl_r),
            close_trade=close_trade,
        )
        if not recorded:
            return False

        current_remaining = float(trade.get("remaining_fraction") or 0.0)
        trade["remaining_fraction"] = max(0.0, current_remaining - fraction_closed)
        trade["realized_pnl_usd"] = float(trade.get("realized_pnl_usd") or 0.0) + float(pnl_usd)
        trade["realized_r"] = float(trade.get("realized_r") or 0.0) + float(pnl_r)

        if close_trade:
            trade["status"] = "CLOSED"
            trade["closed_at"] = event_at

        return True

    def _pending_targets(self, trade: dict[str, Any]) -> list[tuple[str, float, float, str]]:
        targets: list[tuple[str, float, float, str]] = []
        if trade.get("tp1_hit_at") is None:
            targets.append(("TP1", float(trade["tp1"]), float(self.settings.tp1_allocation), "tp1_hit_at"))
        if trade.get("tp2_hit_at") is None:
            targets.append(("TP2", float(trade["tp2"]), float(self.settings.tp2_allocation), "tp2_hit_at"))
        if trade.get("tp3_hit_at") is None:
            targets.append(("TP3", float(trade["tp3"]), float(self.settings.tp3_allocation), "tp3_hit_at"))
        return targets

    def _sl_touched(self, side: str, candle: Candle, stop_loss: float) -> bool:
        if side == "LONG":
            return candle.low <= stop_loss
        return candle.high >= stop_loss

    def _tp_touched(self, side: str, candle: Candle, target: float) -> bool:
        if side == "LONG":
            return candle.high >= target
        return candle.low <= target

    def _handle_window_open(self, payload: dict[str, Any]) -> None:
        signal = payload.get("signal") or {}
        trade_plan = payload.get("trade_plan") or {}
        if not trade_plan:
            return

        state = str(signal.get("state") or "")
        if state not in {"HIGH", "VERY_HIGH"}:
            return

        side = str(trade_plan.get("side") or "")
        if side not in {"LONG", "SHORT"}:
            return

        diagnostics = payload.get("trade_diagnostics") or {}
        daily_candles_used = int(
            diagnostics.get("daily_candles_used")
            or payload.get("swing_range", {}).get("daily_candles_used")
            or 0
        )
        created_at = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())

        fingerprint = self._signal_fingerprint(
            state=state,
            trade_plan=trade_plan,
            diagnostics=diagnostics,
            daily_candles_used=daily_candles_used,
        )

        setup_ctx = payload.get("setup_context") or {}
        setup_id = setup_ctx.get("setup_id")
        if not setup_id:
            # Fallback for synthetic unit test payloads lacking setup_context
            setup_id = f"test_setup_{fingerprint[:16]}"

        opp = self.repository.get_opportunity(setup_id)
        if opp is None:
            supp = float(setup_ctx.get("support") or payload.get("swing_range", {}).get("support") or trade_plan["sl"])
            res = float(setup_ctx.get("resistance") or payload.get("swing_range", {}).get("resistance") or trade_plan["entry"])
            price = float(setup_ctx.get("origin_price") or payload.get("market", {}).get("price") or trade_plan["entry"])
            try:
                self.repository.create_opportunity(
                    setup_id=setup_id,
                    coin=self.settings.coin,
                    side=side,
                    support=supp,
                    resistance=res,
                    origin_price=price,
                    created_at=created_at,
                )
                opp = self.repository.get_opportunity(setup_id)
            except Exception as exc:
                self.logger.warning("Failed to auto-register opportunity for setup %s: %s", setup_id, exc)

        # Fail-closed barriers before attempting trade execution
        if self.repository.has_trade_for_setup(setup_id):
            self.logger.info("Setup %s already traded; suppressing duplicate execution", setup_id)
            return

        if opp is None or opp["status"] != "ACTIVE_UNTRADED":
            self.logger.info(
                "Setup %s status is %s; cannot execute trade",
                setup_id,
                opp.get("status") if opp else "None",
            )
            return

        try:
            signal_id = self.repository.execute_opportunity_trade(
                setup_id=setup_id,
                fingerprint=fingerprint,
                created_at=created_at,
                side=side,
                state_at_entry=state,
                daily_swing_candles_at_signal=daily_candles_used,
                plan=trade_plan,
            )
        except Exception as exc:
            self.logger.exception("Failed to execute opportunity trade for setup %s: %s", setup_id, exc)
            return

        self._send_trade_alert(
            signal_id=signal_id,
            setup_id=setup_id,
            trade_plan=trade_plan,
        )

    def _signal_fingerprint(
        self,
        *,
        state: str,
        trade_plan: dict[str, Any],
        diagnostics: dict[str, Any],
        daily_candles_used: int,
    ) -> str:
        support = ((diagnostics.get("support") or {}).get("selected_level"))
        resistance = ((diagnostics.get("resistance") or {}).get("selected_level"))
        analysis_from = ((diagnostics.get("analysis_window") or {}).get("from"))
        analysis_to = ((diagnostics.get("analysis_window") or {}).get("to"))

        raw = "|".join(
            [
                self.settings.coin,
                str(trade_plan.get("side")),
                state,
                f"{float(trade_plan.get('entry', 0.0)):.2f}",
                f"{float(trade_plan.get('sl', 0.0)):.2f}",
                f"{float(trade_plan.get('tp1', 0.0)):.2f}",
                f"{float(trade_plan.get('tp2', 0.0)):.2f}",
                f"{float(trade_plan.get('tp3', 0.0)):.2f}",
                f"{float(support or 0.0):.2f}",
                f"{float(resistance or 0.0):.2f}",
                str(analysis_from or ""),
                str(analysis_to or ""),
                str(daily_candles_used),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _send_trade_alert(
        self,
        *,
        signal_id: int,
        setup_id: str,
        trade_plan: dict[str, Any],
    ) -> None:
        event_key = f"TRADE_ALERT:{setup_id}"
        if self.repository.has_successful_telegram_event(event_key):
            return

        if not self.settings.telegram_enabled or not self.telegram_notifier.configured:
            return

        message = self._build_trade_alert_message(trade_plan=trade_plan)

        try:
            message_id = self.telegram_notifier.send_message(message)
            self.repository.record_telegram_event(
                event_type="TRADE_ALERT",
                event_key=event_key,
                success=True,
                telegram_message_id=message_id,
                signal_id=signal_id,
            )
        except Exception as exc:
            self.logger.warning("Trade alert delivery failed: %s", exc)
            self.repository.record_telegram_event(
                event_type="TRADE_ALERT",
                event_key=event_key,
                success=False,
                error_message=exc.__class__.__name__,
                signal_id=signal_id,
            )

    def retry_pending_trade_alerts(self) -> None:
        if not self.settings.telegram_enabled or not self.telegram_notifier.configured:
            return

        pending = self.repository.list_trades_missing_successful_alert()
        for trade in pending:
            setup_id = trade.get("setup_id")
            if not setup_id:
                continue

            plan = {
                "side": trade["side"],
                "entry": trade["entry_reference"],
                "sl": trade["stop_loss"],
                "tp1": trade["tp1"],
                "tp2": trade["tp2"],
                "tp3": trade["tp3"],
                "margin_usd": trade["margin_usd"],
                "leverage": trade["leverage"],
            }
            self._send_trade_alert(
                signal_id=int(trade["id"]),
                setup_id=setup_id,
                trade_plan=plan,
            )

    def _build_trade_alert_message(self, *, trade_plan: dict[str, Any]) -> str:
        side = str(trade_plan.get("side") or "-")
        entry = float(trade_plan.get("entry") or 0.0)

        return "\n".join(
            [
                f"\U0001F6A8 BTC SWING \u00b7 {side}",
                "",
                f"Precio ref: {format_money(entry, signed=False)}",
                f"SL: {format_money(float(trade_plan.get('sl') or 0.0), signed=False)}",
                "",
                f"TP1: {format_money(float(trade_plan.get('tp1') or 0.0), signed=False)} \u00b7 30%",
                f"TP2: {format_money(float(trade_plan.get('tp2') or 0.0), signed=False)} \u00b7 30%",
                f"TP3: {format_money(float(trade_plan.get('tp3') or 0.0), signed=False)} \u00b7 40%",
                "",
                f"Margen: {format_money(float(trade_plan.get('margin_usd') or 0.0), signed=False)}",
                f"Leverage: {int(trade_plan.get('leverage') or 0)}x",
            ]
        )

    def _compute_open_pnl(self) -> float:
        open_trades = self.repository.list_open_trades()
        if not open_trades:
            return 0.0

        current_price = self.market_client_factory().get_mid(self.settings.coin)
        total_open_pnl = 0.0

        for trade in open_trades:
            remaining_fraction = float(trade.get("remaining_fraction") or 0.0)
            if remaining_fraction <= 1e-9:
                continue

            total_open_pnl += calculate_fraction_pnl_usd(
                side=str(trade["side"]),
                entry=float(trade["entry_reference"]),
                exit_price=float(current_price),
                notional_usd=float(trade["notional_usd"]),
                fraction_closed=remaining_fraction,
            )

        return total_open_pnl
