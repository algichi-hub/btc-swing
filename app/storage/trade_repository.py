from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any

from app.storage.database import connect


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(x) for x in obj]
    return obj


class TradeRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def get_runtime_state(self, key: str) -> str | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                "SELECT value FROM engine_runtime_state WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row["value"])

    def set_runtime_state(self, key: str, value: str) -> None:
        timestamp = _utc_now_iso()
        with connect(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO engine_runtime_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, timestamp),
            )

    def get_runtime_bool(self, key: str) -> bool | None:
        value = self.get_runtime_state(key)
        if value is None:
            return None
        return value == "1"

    def set_runtime_bool(self, key: str, value: bool) -> None:
        self.set_runtime_state(key, "1" if value else "0")

    def has_successful_telegram_event(self, event_key: str) -> bool:
        with connect(self.database_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM telegram_events WHERE event_key = ? AND success = 1",
                (event_key,),
            ).fetchone()
        return row is not None

    def record_telegram_event(
        self,
        *,
        event_type: str,
        event_key: str,
        success: bool,
        telegram_message_id: str | None = None,
        error_message: str | None = None,
        signal_id: int | None = None,
        sent_at: str | None = None,
    ) -> None:
        timestamp = sent_at or _utc_now_iso()
        with connect(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO telegram_events (
                    event_type,
                    event_key,
                    sent_at,
                    success,
                    telegram_message_id,
                    error_message,
                    signal_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_key) DO UPDATE SET
                    event_type = excluded.event_type,
                    sent_at = excluded.sent_at,
                    success = excluded.success,
                    telegram_message_id = excluded.telegram_message_id,
                    error_message = excluded.error_message,
                    signal_id = excluded.signal_id
                """,
                (
                    event_type,
                    event_key,
                    timestamp,
                    1 if success else 0,
                    telegram_message_id,
                    error_message,
                    signal_id,
                ),
            )

    def last_successful_telegram_event_at(self, event_type: str) -> str | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT sent_at
                FROM telegram_events
                WHERE event_type = ? AND success = 1
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (event_type,),
            ).fetchone()
        return None if row is None else str(row["sent_at"])

    def create_opportunity(
        self,
        *,
        setup_id: str,
        coin: str,
        side: str,
        support: float,
        resistance: float,
        origin_price: float,
        created_at: str | None = None,
    ) -> None:
        timestamp = created_at or _utc_now_iso()
        with connect(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO trade_opportunities (
                    setup_id,
                    coin,
                    side,
                    support,
                    resistance,
                    origin_price,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE_UNTRADED', ?)
                """,
                (
                    str(setup_id),
                    str(coin),
                    str(side),
                    float(support),
                    float(resistance),
                    float(origin_price),
                    timestamp,
                ),
            )

    def get_opportunity(self, setup_id: str) -> dict[str, Any] | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT setup_id, coin, side, support, resistance, origin_price,
                       status, created_at, executed_at, invalidated_at, invalidation_reason
                FROM trade_opportunities
                WHERE setup_id = ?
                """,
                (str(setup_id),),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_active_opportunity(self, coin: str = "BTC") -> dict[str, Any] | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT setup_id, coin, side, support, resistance, origin_price,
                       status, created_at, executed_at, invalidated_at, invalidation_reason
                FROM trade_opportunities
                WHERE coin = ? AND status IN ('ACTIVE_UNTRADED', 'ACTIVE_TRADED')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(coin),),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def mark_opportunity_invalidated(
        self,
        setup_id: str,
        *,
        reason: str,
        invalidated_at: str | None = None,
    ) -> bool:
        timestamp = invalidated_at or _utc_now_iso()
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                UPDATE trade_opportunities
                SET status = 'INVALIDATED',
                    invalidated_at = ?,
                    invalidation_reason = ?
                WHERE setup_id = ? AND status IN ('ACTIVE_UNTRADED', 'ACTIVE_TRADED')
                """,
                (timestamp, str(reason), str(setup_id)),
            )
            return cursor.rowcount > 0

    def has_trade_for_setup(self, setup_id: str) -> bool:
        with connect(self.database_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM trade_signals WHERE setup_id = ? LIMIT 1",
                (str(setup_id),),
            ).fetchone()
        return row is not None

    def execute_opportunity_trade(
        self,
        *,
        setup_id: str,
        fingerprint: str,
        created_at: str,
        side: str,
        state_at_entry: str,
        daily_swing_candles_at_signal: int,
        plan: dict[str, Any],
    ) -> int:
        with connect(self.database_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            # Barrier 1: verify opportunity exists and is ACTIVE_UNTRADED
            opp = conn.execute(
                "SELECT status FROM trade_opportunities WHERE setup_id = ?",
                (str(setup_id),),
            ).fetchone()
            if opp is None:
                raise ValueError(f"Opportunity {setup_id} does not exist in trade_opportunities")
            if str(opp["status"]) != "ACTIVE_UNTRADED":
                raise ValueError(
                    f"Opportunity {setup_id} cannot be executed: status is {opp['status']} (must be ACTIVE_UNTRADED)"
                )

            # Barrier 2: verify no existing trade for this setup_id (OPEN or CLOSED)
            existing = conn.execute(
                "SELECT id FROM trade_signals WHERE setup_id = ?",
                (str(setup_id),),
            ).fetchone()
            if existing is not None:
                raise ValueError(f"Trade already exists for setup {setup_id} (signal_id={existing['id']})")

            # Barrier 3: insert into trade_signals with setup_id (enforced by DB unique index)
            cursor = conn.execute(
                """
                INSERT INTO trade_signals (
                    setup_id,
                    created_at,
                    origin,
                    side,
                    state_at_entry,
                    daily_swing_candles_at_signal,
                    entry_reference,
                    stop_loss,
                    tp1,
                    tp2,
                    tp3,
                    rr1,
                    rr2,
                    rr3,
                    weighted_rr,
                    statistical_samples,
                    margin_usd,
                    leverage,
                    notional_usd,
                    status,
                    fingerprint,
                    remaining_fraction,
                    realized_pnl_usd,
                    realized_r
                )
                VALUES (?, ?, 'PAPER', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 'OPEN', ?, 1.0, 0.0, 0.0)
                """,
                (
                    str(setup_id),
                    created_at,
                    side,
                    state_at_entry,
                    int(daily_swing_candles_at_signal),
                    float(plan["entry"]),
                    float(plan["sl"]),
                    float(plan["tp1"]),
                    float(plan["tp2"]),
                    float(plan["tp3"]),
                    float(plan["rr1"]),
                    float(plan["rr2"]),
                    float(plan["rr3"]),
                    float(plan["weighted_rr"]),
                    float(plan["margin_usd"]),
                    int(plan["leverage"]),
                    float(plan["notional_usd"]),
                    fingerprint,
                ),
            )
            signal_id = int(cursor.lastrowid)

            # Transition opportunity to ACTIVE_TRADED
            upd = conn.execute(
                """
                UPDATE trade_opportunities
                SET status = 'ACTIVE_TRADED',
                    executed_at = ?
                WHERE setup_id = ? AND status = 'ACTIVE_UNTRADED'
                """,
                (created_at, str(setup_id)),
            )
            if upd.rowcount != 1:
                raise RuntimeError(f"Failed to update opportunity {setup_id} status to ACTIVE_TRADED")

            return signal_id

    def list_trades_missing_successful_alert(self) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.setup_id, s.side, s.entry_reference, s.stop_loss,
                       s.tp1, s.tp2, s.tp3, s.margin_usd, s.leverage, s.notional_usd,
                       s.created_at, s.fingerprint
                FROM trade_signals s
                WHERE s.origin = 'PAPER'
                  AND s.setup_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM telegram_events t
                      WHERE t.event_key = ('TRADE_ALERT:' || s.setup_id)
                        AND t.success = 1
                  )
                ORDER BY s.id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_paper_trade(
        self,
        *,
        fingerprint: str,
        created_at: str,
        side: str,
        state_at_entry: str,
        daily_swing_candles_at_signal: int,
        plan: dict[str, Any],
        setup_id: str | None = None,
    ) -> int:
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO trade_signals (
                    setup_id,
                    created_at,
                    origin,
                    side,
                    state_at_entry,
                    daily_swing_candles_at_signal,
                    entry_reference,
                    stop_loss,
                    tp1,
                    tp2,
                    tp3,
                    rr1,
                    rr2,
                    rr3,
                    weighted_rr,
                    statistical_samples,
                    margin_usd,
                    leverage,
                    notional_usd,
                    status,
                    fingerprint,
                    remaining_fraction,
                    realized_pnl_usd,
                    realized_r
                )
                VALUES (?, ?, 'PAPER', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 'OPEN', ?, 1.0, 0.0, 0.0)
                """,
                (
                    setup_id,
                    created_at,
                    side,
                    state_at_entry,
                    int(daily_swing_candles_at_signal),
                    float(plan["entry"]),
                    float(plan["sl"]),
                    float(plan["tp1"]),
                    float(plan["tp2"]),
                    float(plan["tp3"]),
                    float(plan["rr1"]),
                    float(plan["rr2"]),
                    float(plan["rr3"]),
                    float(plan["weighted_rr"]),
                    float(plan["margin_usd"]),
                    int(plan["leverage"]),
                    float(plan["notional_usd"]),
                    fingerprint,
                ),
            )
            if cursor.rowcount > 0:
                return int(cursor.lastrowid)

            existing = conn.execute(
                "SELECT id FROM trade_signals WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing is None:
                raise RuntimeError("Failed to create or load paper trade")
            return int(existing["id"])

    def list_open_trades(self) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    setup_id,
                    created_at,
                    side,
                    state_at_entry,
                    daily_swing_candles_at_signal,
                    entry_reference,
                    stop_loss,
                    tp1,
                    tp2,
                    tp3,
                    rr1,
                    rr2,
                    rr3,
                    weighted_rr,
                    margin_usd,
                    leverage,
                    notional_usd,
                    status,
                    fingerprint,
                    tp1_hit_at,
                    tp2_hit_at,
                    tp3_hit_at,
                    sl_hit_at,
                    remaining_fraction,
                    realized_pnl_usd,
                    realized_r,
                    closed_at,
                    last_processed_candle_close_ms
                FROM trade_signals
                WHERE origin = 'PAPER' AND status = 'OPEN'
                ORDER BY id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_trade_history(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))

        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    setup_id,
                    created_at,
                    origin,
                    side,
                    state_at_entry,
                    entry_reference,
                    stop_loss,
                    tp1,
                    tp2,
                    tp3,
                    rr1,
                    rr2,
                    rr3,
                    weighted_rr,
                    margin_usd,
                    leverage,
                    notional_usd,
                    status,
                    tp1_hit_at,
                    tp2_hit_at,
                    tp3_hit_at,
                    sl_hit_at,
                    remaining_fraction,
                    realized_pnl_usd,
                    realized_r,
                    closed_at
                FROM trade_signals
                WHERE status = 'CLOSED'
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def reset_operational_data(self) -> None:
        """
        Safely and transactionally clears operational and historical trading data.
        Deletes trade_events, trade_results, operational telegram_events,
        trade_signals, trade_opportunities, engine_snapshots, and engine_runtime_state.
        Preserves app_settings and system configuration.
        """
        with connect(self.database_path) as conn:
            conn.execute("DELETE FROM trade_events")
            conn.execute("DELETE FROM trade_results")
            conn.execute("DELETE FROM telegram_events WHERE signal_id IS NOT NULL OR event_type != 'TEST'")
            conn.execute("DELETE FROM trade_signals")
            conn.execute("DELETE FROM trade_opportunities")
            conn.execute("DELETE FROM engine_snapshots")
            conn.execute("DELETE FROM engine_runtime_state")

    def get_daily_cumulative_pnl(
        self,
        days: int | None = None,
        to_date: Any = None,
    ) -> list[dict[str, Any]]:
        """
        Calculate daily realized PnL and cumulative PnL from CLOSED trades.
        Grouped by UTC calendar day based on closed_at.
        Includes calendar days without trades with daily_pnl=0.0 and flat cumulative_pnl.
        Cumulative PnL is computed from the entire history; if 'days' is specified,
        only the last 'days' are returned without resetting cumulative PnL to 0.
        """
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT realized_pnl_usd, closed_at
                FROM trade_signals
                WHERE status = 'CLOSED' AND closed_at IS NOT NULL
                ORDER BY closed_at ASC, id ASC
                """
            ).fetchall()

        if not rows:
            return []

        daily_sums: dict[date, float] = {}
        daily_counts: dict[date, int] = {}
        all_dates: list[date] = []

        for row in rows:
            closed_at_str = str(row["closed_at"])
            dt = datetime.fromisoformat(closed_at_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            d = dt.astimezone(timezone.utc).date()
            pnl = float(row["realized_pnl_usd"] or 0.0)

            daily_sums[d] = daily_sums.get(d, 0.0) + pnl
            daily_counts[d] = daily_counts.get(d, 0) + 1
            all_dates.append(d)

        start_date = min(all_dates)
        if to_date is not None:
            if isinstance(to_date, str):
                end_date = date.fromisoformat(to_date)
            elif isinstance(to_date, datetime):
                end_date = to_date.astimezone(timezone.utc).date()
            else:
                end_date = to_date
        else:
            end_date = max(all_dates)

        if end_date < start_date:
            end_date = start_date

        points: list[dict[str, Any]] = []
        current_date = start_date
        running_cumulative = 0.0

        while current_date <= end_date:
            day_pnl = daily_sums.get(current_date, 0.0)
            running_cumulative += day_pnl
            points.append({
                "date": current_date.isoformat(),
                "daily_pnl": round(day_pnl, 2),
                "cumulative_pnl": round(running_cumulative, 2),
                "trade_count": daily_counts.get(current_date, 0),
            })
            current_date += timedelta(days=1)

        if days is not None and days > 0:
            if len(points) > days:
                return points[-days:]

        return points

    def list_trade_events(self, signal_id: int) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    signal_id,
                    event_at,
                    event_type,
                    price,
                    fraction_closed,
                    pnl_usd,
                    pnl_r
                FROM trade_events
                WHERE signal_id = ?
                ORDER BY event_at ASC, id ASC
                """,
                (int(signal_id),),
            ).fetchall()

        return [dict(row) for row in rows]

    def mark_last_processed_candle(self, signal_id: int, candle_close_ms: int) -> None:
        with connect(self.database_path) as conn:
            conn.execute(
                """
                UPDATE trade_signals
                SET last_processed_candle_close_ms = ?
                WHERE id = ?
                """,
                (int(candle_close_ms), int(signal_id)),
            )

    def record_exit_event(
        self,
        *,
        signal_id: int,
        event_type: str,
        event_at: str,
        price: float,
        fraction_closed: float,
        pnl_usd: float,
        pnl_r: float,
        close_trade: bool,
    ) -> bool:
        hit_column_by_type = {
            "TP1": "tp1_hit_at",
            "TP2": "tp2_hit_at",
            "TP3": "tp3_hit_at",
            "SL": "sl_hit_at",
        }
        hit_column = hit_column_by_type.get(event_type)

        if fraction_closed <= 0:
            return False

        with connect(self.database_path) as conn:
            columns = "status, remaining_fraction, realized_pnl_usd, realized_r"
            if hit_column:
                columns = f"{columns}, {hit_column}"
            row = conn.execute(
                f"SELECT {columns} FROM trade_signals WHERE id = ?",
                (int(signal_id),),
            ).fetchone()

            if row is None:
                return False
            if str(row["status"]) == "CLOSED":
                return False
            if hit_column and row[hit_column] is not None:
                return False

            insert_cursor = conn.execute(
                """
                INSERT OR IGNORE INTO trade_events (
                    signal_id,
                    event_at,
                    event_type,
                    price,
                    fraction_closed,
                    pnl_usd,
                    pnl_r
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(signal_id),
                    event_at,
                    event_type,
                    float(price),
                    float(fraction_closed),
                    float(pnl_usd),
                    float(pnl_r),
                ),
            )
            if insert_cursor.rowcount == 0:
                return False

            current_remaining = float(row["remaining_fraction"] or 0.0)
            current_pnl = float(row["realized_pnl_usd"] or 0.0)
            current_r = float(row["realized_r"] or 0.0)

            remaining_fraction = max(0.0, current_remaining - float(fraction_closed))
            should_close = close_trade or remaining_fraction <= 1e-9

            update_parts = [
                "remaining_fraction = ?",
                "realized_pnl_usd = ?",
                "realized_r = ?",
            ]
            update_values: list[Any] = [
                0.0 if should_close else remaining_fraction,
                current_pnl + float(pnl_usd),
                current_r + float(pnl_r),
            ]

            if hit_column:
                update_parts.append(f"{hit_column} = ?")
                update_values.append(event_at)

            if should_close:
                update_parts.append("status = 'CLOSED'")
                update_parts.append("closed_at = ?")
                update_values.append(event_at)

            update_values.append(int(signal_id))

            conn.execute(
                f"UPDATE trade_signals SET {', '.join(update_parts)} WHERE id = ?",
                tuple(update_values),
            )

        return True

    def count_signals_in_period(self, period_start: str, period_end: str) -> int:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM trade_signals
                WHERE origin = 'PAPER'
                  AND created_at >= ?
                  AND created_at < ?
                """,
                (period_start, period_end),
            ).fetchone()
        return int(row["total"] if row else 0)

    def count_closed_trades_in_period(self, period_start: str, period_end: str) -> int:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM trade_signals
                WHERE origin = 'PAPER'
                  AND status = 'CLOSED'
                  AND closed_at IS NOT NULL
                  AND closed_at >= ?
                  AND closed_at < ?
                """,
                (period_start, period_end),
            ).fetchone()
        return int(row["total"] if row else 0)

    def count_open_trades(self) -> int:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM trade_signals
                WHERE origin = 'PAPER' AND status = 'OPEN'
                """
            ).fetchone()
        return int(row["total"] if row else 0)

    def count_trade_events_in_period(self, event_type: str, period_start: str, period_end: str) -> int:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM trade_events
                WHERE event_type = ?
                  AND event_at >= ?
                  AND event_at < ?
                """,
                (event_type, period_start, period_end),
            ).fetchone()
        return int(row["total"] if row else 0)

    def sum_realized_pnl_in_period(self, period_start: str, period_end: str) -> float:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(pnl_usd), 0.0) AS total
                FROM trade_events
                WHERE event_at >= ?
                  AND event_at < ?
                """,
                (period_start, period_end),
            ).fetchone()
        return float(row["total"] if row else 0.0)

    def average_weighted_rr_in_period(self, period_start: str, period_end: str) -> float | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT AVG(weighted_rr) AS avg_rr
                FROM trade_signals
                WHERE origin = 'PAPER'
                  AND created_at >= ?
                  AND created_at < ?
                """,
                (period_start, period_end),
            ).fetchone()
        if row is None or row["avg_rr"] is None:
            return None
        return float(row["avg_rr"])

    def record_engine_snapshot(self, payload: dict[str, Any]) -> int:
        created_at = str(payload.get("timestamp") or _utc_now_iso())
        algorithm_version = str(payload.get("algorithm_version") or "V2.1-beta")
        market = payload.get("market") or {}
        price = market.get("price")
        price_val = float(price) if price is not None and math.isfinite(float(price)) else None

        signal = payload.get("signal") or {}
        signal_state = str(signal.get("state") or "UNKNOWN")
        signal_side = signal.get("side")
        signal_side_val = str(signal_side) if signal_side is not None else None

        trade_window_open = 1 if payload.get("trade_window_open") else 0
        block_reason = payload.get("block_reason")
        block_reason_val = str(block_reason) if block_reason is not None else None

        setup_ctx = payload.get("setup_context") or {}
        setup_active = 1 if setup_ctx.get("active") else 0
        setup_id = setup_ctx.get("setup_id")
        setup_id_val = str(setup_id) if setup_id is not None else None

        sanitized_payload = _sanitize_for_json(payload)
        snapshot_json = json.dumps(sanitized_payload, ensure_ascii=False, sort_keys=True)

        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO engine_snapshots (
                    created_at,
                    algorithm_version,
                    price,
                    signal_state,
                    signal_side,
                    trade_window_open,
                    block_reason,
                    setup_id,
                    setup_active,
                    snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    algorithm_version,
                    price_val,
                    signal_state,
                    signal_side_val,
                    trade_window_open,
                    block_reason_val,
                    setup_id_val,
                    setup_active,
                    snapshot_json,
                ),
            )
            return int(cursor.lastrowid)

    def count_engine_snapshots(self) -> int:
        with connect(self.database_path) as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM engine_snapshots").fetchone()
        return int(row["total"] if row else 0)

    def get_latest_engine_snapshot(self) -> dict[str, Any] | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT id, created_at, algorithm_version, price, signal_state, signal_side,
                       trade_window_open, block_reason, setup_id, setup_active, snapshot_json
                FROM engine_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "created_at": str(row["created_at"]),
            "algorithm_version": str(row["algorithm_version"]),
            "price": float(row["price"]) if row["price"] is not None else None,
            "signal_state": str(row["signal_state"]),
            "signal_side": str(row["signal_side"]) if row["signal_side"] is not None else None,
            "trade_window_open": bool(row["trade_window_open"]),
            "block_reason": str(row["block_reason"]) if row["block_reason"] is not None else None,
            "setup_id": str(row["setup_id"]) if row["setup_id"] is not None else None,
            "setup_active": bool(row["setup_active"]),
            "snapshot_json": str(row["snapshot_json"]),
            "data": json.loads(row["snapshot_json"]),
        }

    def get_latest_snapshot_for_setup(self, setup_id: str) -> dict[str, Any] | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT id, created_at, algorithm_version, price, signal_state, signal_side,
                       trade_window_open, block_reason, setup_id, setup_active, snapshot_json
                FROM engine_snapshots
                WHERE setup_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(setup_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "created_at": str(row["created_at"]),
            "algorithm_version": str(row["algorithm_version"]),
            "price": float(row["price"]) if row["price"] is not None else None,
            "signal_state": str(row["signal_state"]),
            "signal_side": str(row["signal_side"]) if row["signal_side"] is not None else None,
            "trade_window_open": bool(row["trade_window_open"]),
            "block_reason": str(row["block_reason"]) if row["block_reason"] is not None else None,
            "setup_id": str(row["setup_id"]) if row["setup_id"] is not None else None,
            "setup_active": bool(row["setup_active"]),
            "snapshot_json": str(row["snapshot_json"]),
        }

    def get_engine_snapshot_by_id(self, snapshot_id: int) -> dict[str, Any] | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT id, created_at, algorithm_version, price, signal_state, signal_side,
                       trade_window_open, block_reason, setup_id, setup_active, snapshot_json
                FROM engine_snapshots
                WHERE id = ?
                """,
                (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        raw_json = str(row["snapshot_json"])
        try:
            parsed_data = json.loads(raw_json)
        except Exception:
            parsed_data = None

        return {
            "id": int(row["id"]),
            "created_at": str(row["created_at"]),
            "algorithm_version": str(row["algorithm_version"]),
            "price": float(row["price"]) if row["price"] is not None else None,
            "signal_state": str(row["signal_state"]),
            "signal_side": str(row["signal_side"]) if row["signal_side"] is not None else None,
            "trade_window_open": bool(row["trade_window_open"]),
            "block_reason": str(row["block_reason"]) if row["block_reason"] is not None else None,
            "setup_id": str(row["setup_id"]) if row["setup_id"] is not None else None,
            "setup_active": bool(row["setup_active"]),
            "snapshot_json": raw_json,
            "data": parsed_data,
        }

    def list_engine_snapshots(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        setup_id: str | None = None,
        signal_state: str | None = None,
        signal_side: str | None = None,
        block_reason: str | None = None,
        trade_window_open: bool | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []

        if setup_id is not None:
            conditions.append("setup_id = ?")
            params.append(str(setup_id))

        if signal_state is not None:
            conditions.append("signal_state = ?")
            params.append(str(signal_state))

        if signal_side is not None:
            conditions.append("signal_side = ?")
            params.append(str(signal_side))

        if block_reason is not None:
            conditions.append("block_reason = ?")
            params.append(str(block_reason))

        if trade_window_open is not None:
            conditions.append("trade_window_open = ?")
            params.append(1 if trade_window_open else 0)

        if from_ts is not None:
            conditions.append("created_at >= ?")
            params.append(str(from_ts))

        if to_ts is not None:
            conditions.append("created_at <= ?")
            params.append(str(to_ts))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))

        with connect(self.database_path) as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) AS total FROM engine_snapshots {where_clause}",
                tuple(params),
            ).fetchone()
            total = int(count_row["total"] if count_row else 0)

            query = f"""
                SELECT id, created_at, algorithm_version, price, signal_state, signal_side,
                       trade_window_open, block_reason, setup_id, setup_active, snapshot_json
                FROM engine_snapshots
                {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(query, tuple(params + [safe_limit, safe_offset])).fetchall()

        items = []
        for row in rows:
            raw_json = str(row["snapshot_json"])
            try:
                parsed_data = json.loads(raw_json)
            except Exception:
                parsed_data = None

            items.append({
                "id": int(row["id"]),
                "created_at": str(row["created_at"]),
                "algorithm_version": str(row["algorithm_version"]),
                "price": float(row["price"]) if row["price"] is not None else None,
                "signal_state": str(row["signal_state"]),
                "signal_side": str(row["signal_side"]) if row["signal_side"] is not None else None,
                "trade_window_open": bool(row["trade_window_open"]),
                "block_reason": str(row["block_reason"]) if row["block_reason"] is not None else None,
                "setup_id": str(row["setup_id"]) if row["setup_id"] is not None else None,
                "setup_active": bool(row["setup_active"]),
                "data": parsed_data,
            })

        return {
            "items": items,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
        }

    def list_engine_snapshots_for_setup(self, setup_id: str) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, algorithm_version, price, signal_state, signal_side,
                       trade_window_open, block_reason, setup_id, setup_active, snapshot_json
                FROM engine_snapshots
                WHERE setup_id = ?
                ORDER BY id ASC
                """,
                (str(setup_id),),
            ).fetchall()

        items = []
        for row in rows:
            raw_json = str(row["snapshot_json"])
            try:
                parsed_data = json.loads(raw_json)
            except Exception:
                parsed_data = None

            items.append({
                "id": int(row["id"]),
                "created_at": str(row["created_at"]),
                "algorithm_version": str(row["algorithm_version"]),
                "price": float(row["price"]) if row["price"] is not None else None,
                "signal_state": str(row["signal_state"]),
                "signal_side": str(row["signal_side"]) if row["signal_side"] is not None else None,
                "trade_window_open": bool(row["trade_window_open"]),
                "block_reason": str(row["block_reason"]) if row["block_reason"] is not None else None,
                "setup_id": str(row["setup_id"]) if row["setup_id"] is not None else None,
                "setup_active": bool(row["setup_active"]),
                "snapshot_json": raw_json,
                "data": parsed_data,
            })
        return items


STATE_SEVERITY_ORDER = {
    "NO_TRADE": 1,
    "IDLE": 1,
    "WATCH": 2,
    "CONFIRMED": 3,
    "HIGH": 4,
    "VERY_HIGH": 5,
}


def build_setup_timeline_response(setup_id: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    timeline = []
    highest_state = "NO_TRADE"
    highest_score = 0
    first_window_open_at: str | None = None
    invalidated_seen = False

    for s in snapshots:
        d = s.get("data") or {}
        sig_state = s["signal_state"]
        score = STATE_SEVERITY_ORDER.get(sig_state, 0)
        if score > highest_score:
            highest_score = score
            highest_state = sig_state

        if s["trade_window_open"] and first_window_open_at is None:
            first_window_open_at = s["created_at"]

        if s["block_reason"] == "SETUP_INVALIDATED":
            invalidated_seen = True

        swing = d.get("swing_range") or {}
        diag = d.get("trade_diagnostics") or {}
        op_range = d.get("operational_range") or {}
        supp_obj = op_range.get("support") or {}
        res_obj = op_range.get("resistance") or {}
        setup_ctx = d.get("setup_context") or {}
        sig = d.get("signal") or {}
        tp = d.get("trade_plan")

        timeline.append({
            "snapshot_id": s["id"],
            "timestamp": s["created_at"],
            "algorithm_version": s["algorithm_version"],
            "price": s["price"],
            "signal_state": s["signal_state"],
            "signal_side": s["signal_side"],
            "trade_window_open": s["trade_window_open"],
            "block_reason": s["block_reason"],
            "structural": {
                "support": swing.get("support"),
                "resistance": swing.get("resistance"),
                "daily_candles_used": swing.get("daily_candles_used"),
                "confirmations_support": (diag.get("support") or {}).get("score"),
                "confirmations_resistance": (diag.get("resistance") or {}).get("score"),
            },
            "live_operational": {
                "support": supp_obj.get("price"),
                "resistance": res_obj.get("price"),
                "support_source": supp_obj.get("source"),
                "resistance_source": res_obj.get("source"),
                "support_distance_pct": supp_obj.get("distance_pct"),
                "resistance_distance_pct": res_obj.get("distance_pct"),
                "is_valid": op_range.get("is_valid"),
            },
            "setup": {
                "setup_id": setup_ctx.get("setup_id") or s["setup_id"],
                "active": bool(setup_ctx.get("active", s["setup_active"])),
                "side": setup_ctx.get("side") or s["signal_side"],
                "started_at": setup_ctx.get("started_at"),
                "support": setup_ctx.get("support"),
                "resistance": setup_ctx.get("resistance"),
                "midpoint": setup_ctx.get("midpoint"),
                "range_width": setup_ctx.get("range_width"),
                "origin_state": setup_ctx.get("origin_state"),
                "origin_price": setup_ctx.get("origin_price"),
                "origin_range_position_pct": setup_ctx.get("origin_range_position_pct"),
                "origin_rejection_level": setup_ctx.get("origin_rejection_level"),
                "origin_config": setup_ctx.get("origin_config") or {},
            },
            "signal": {
                "state": sig.get("state") or s["signal_state"],
                "side": sig.get("side") or s["signal_side"],
                "position_pct": sig.get("position_pct"),
                "weighted_rr": sig.get("weighted_rr"),
                "metrics": sig.get("metrics") or {},
            },
            "trade_plan": {
                "present": tp is not None,
                "plan": tp,
            },
        })

    first_setup = ((snapshots[0].get("data") or {}).get("setup_context") or {}) if snapshots else {}
    summary = {
        "setup_id": setup_id,
        "first_seen_at": snapshots[0]["created_at"] if snapshots else None,
        "last_seen_at": snapshots[-1]["created_at"] if snapshots else None,
        "snapshot_count": len(snapshots),
        "side": first_setup.get("side") or (snapshots[0]["signal_side"] if snapshots else None),
        "origin_support": first_setup.get("support"),
        "origin_resistance": first_setup.get("resistance"),
        "highest_state_seen": highest_state,
        "ever_trade_window_open": any(s["trade_window_open"] for s in snapshots),
        "first_trade_window_open_at": first_window_open_at,
        "last_block_reason": snapshots[-1]["block_reason"] if snapshots else None,
        "invalidated_seen": invalidated_seen,
    }

    return {
        "setup_id": setup_id,
        "summary": summary,
        "timeline": timeline,
    }
