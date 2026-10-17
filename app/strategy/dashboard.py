from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from app.config import ALGORITHM_VERSION, Settings
from app.indicators.stoch_rsi import stochastic_rsi
from app.indicators.volume import relative_volume
from app.models import Candle
from app.portfolio.sizing import NoValidSizingError, recommend_sizing
from app.strategy.block_reason import derive_block_reason
from app.strategy.setup_context import SetupContext, SetupContextManager
from app.strategy.swing_range import (
    OperationalLevel,
    OperationalRangeResult,
    PivotCluster,
    SwingRangeV2Result,
    compute_swing_range_v2,
    derive_operational_range,
    select_operational_level,
    split_daily_candles_for_swing,
)
from app.strategy.trade_plan import reward_risk, validate_trade_plan_topology, weighted_rr

TRADE_WINDOW_STATES = {"HIGH", "VERY_HIGH"}
VOLUME_24H_HOURLY_CANDLES = 24
VOLUME_24H_HOURLY_TIMEFRAME = "1h"

SMA20_FILTERED_PIVOT_CLUSTER_V2 = "SMA20_FILTERED_PIVOT_CLUSTER_V2"


def _iso_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def _date_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()


def classify_stoch_state(stoch_rsi_1h: dict[str, float] | None) -> str | None:
    if stoch_rsi_1h is None:
        return None

    k = stoch_rsi_1h.get("k")
    if k is None:
        return None

    if k >= 80.0:
        return "OVERBOUGHT"
    if k <= 20.0:
        return "OVERSOLD"
    return "NEUTRAL"


def compute_volume_24h_hourly(
    candles_1h: list[Candle],
    candles_to_use: int = VOLUME_24H_HOURLY_CANDLES,
) -> dict[str, Any]:
    if not candles_1h:
        return {
            "timeframe": VOLUME_24H_HOURLY_TIMEFRAME,
            "candles_used": 0,
            "closed_only": True,
            "max_volume_usd": 0.0,
            "bars": [],
        }

    selected = candles_1h[-candles_to_use:]
    max_volume_usd = max(candle.volume * candle.close for candle in selected)
    bars = [
        {
            "timestamp": _iso_from_ms(candle.open_time_ms),
            "volume_btc": round(candle.volume, 8),
            "volume_usd": round(candle.volume * candle.close, 2),
        }
        for candle in selected
    ]

    return {
        "timeframe": VOLUME_24H_HOURLY_TIMEFRAME,
        "candles_used": len(selected),
        "closed_only": True,
        "max_volume_usd": round(max_volume_usd, 2),
        "bars": bars,
    }


def compute_position_pct(price: float, support: float, resistance: float) -> float:
    span = resistance - support
    if span <= 0:
        return 0.0
    return ((price - support) / span) * 100.0


def trade_window_open_for_state(state: str, valid_states: set[str] | None = None) -> bool:
    states = valid_states or TRADE_WINDOW_STATES
    return state.upper() in states


def _build_cluster_pivots(cluster: PivotCluster | None, newest_candle_index: int) -> list[dict[str, Any]]:
    if cluster is None:
        return []

    ordered = sorted(cluster.pivots, key=lambda pivot: pivot.timestamp_ms, reverse=True)
    return [
        {
            "price": round(pivot.price, 2),
            "timestamp": _iso_from_ms(pivot.timestamp_ms),
            "age_sessions": max(0, newest_candle_index - pivot.candle_index),
        }
        for pivot in ordered
    ]


def _build_level_diagnostics(
    *,
    selected_level: float,
    selected_cluster: PivotCluster | None,
    newest_candle_index: int,
) -> dict[str, Any]:
    pivots = _build_cluster_pivots(selected_cluster, newest_candle_index)
    return {
        "selected_level": round(selected_level, 2),
        "score": int(selected_cluster.score if selected_cluster is not None else 0),
        "pivots": pivots,
    }


def build_trade_diagnostics(
    *,
    swing_result: SwingRangeV2Result,
    settings: Settings,
    daily_candles_used: int,
    sma_period: int = 20,
    sma_max_distance_pct: float | None = None,
    cluster_tolerance_pct: float | None = None,
) -> dict[str, Any]:
    analysis_candles = list(swing_result.analysis_candles)

    effective_sma_dist = (
        sma_max_distance_pct
        if sma_max_distance_pct is not None
        else round(settings.swing_sma_max_distance_pct * 100.0, 4)
    )
    if effective_sma_dist <= 0.25:
        effective_sma_dist = round(effective_sma_dist * 100.0, 4)

    effective_cluster_tol = (
        cluster_tolerance_pct
        if cluster_tolerance_pct is not None
        else round(settings.swing_cluster_tolerance_pct * 100.0, 4)
    )
    if effective_cluster_tol <= 0.25:
        effective_cluster_tol = round(effective_cluster_tol * 100.0, 4)

    if not analysis_candles:
        return {
            "method": SMA20_FILTERED_PIVOT_CLUSTER_V2,
            "sma_period": sma_period,
            "sma_max_distance_pct": effective_sma_dist,
            "cluster_tolerance_pct": effective_cluster_tol,
            "daily_candles_used": int(daily_candles_used),
            "analysis_window": {"from": None, "to": None},
            "support": None,
            "resistance": None,
        }

    newest_candle_index = len(analysis_candles) - 1
    support_payload = _build_level_diagnostics(
        selected_level=swing_result.support,
        selected_cluster=swing_result.selected_support_cluster,
        newest_candle_index=newest_candle_index,
    )
    resistance_payload = _build_level_diagnostics(
        selected_level=swing_result.resistance,
        selected_cluster=swing_result.selected_resistance_cluster,
        newest_candle_index=newest_candle_index,
    )

    return {
        "method": SMA20_FILTERED_PIVOT_CLUSTER_V2,
        "sma_period": sma_period,
        "sma_max_distance_pct": effective_sma_dist,
        "cluster_tolerance_pct": effective_cluster_tol,
        "daily_candles_used": int(daily_candles_used),
        "analysis_window": {
            "from": _date_from_ms(analysis_candles[0].open_time_ms),
            "to": _date_from_ms(analysis_candles[-1].open_time_ms),
        },
        "support": support_payload,
        "resistance": resistance_payload,
    }


def select_active_swing_range(candles: list[Candle], price: float, left: int, right: int) -> tuple[float, float]:
    if not candles:
        raise ValueError("At least one daily candle is required to derive an active range")

    swing_result = compute_swing_range_v2(
        analysis_candles=candles,
        warmup_candles=[],
        price=price,
        left=left,
        right=right,
        sma_period=20,
        sma_max_distance_pct=0.05,
        cluster_tolerance_pct=0.025,
    )

    support = swing_result.support
    resistance = swing_result.resistance
    if support >= resistance:
        support = min(candle.low for candle in candles)
        resistance = max(candle.high for candle in candles)

    if support >= resistance:
        resistance = support + max(1.0, abs(support) * 0.001)

    return support, resistance


def _derive_potential_side(position_pct: float) -> str:
    if position_pct <= 35.0:
        return "LONG"
    if position_pct >= 65.0:
        return "SHORT"
    return "NEUTRAL"


def _build_trade_candidate(side: str, entry: float, support: float, resistance: float) -> dict[str, float | str] | None:
    span = resistance - support
    if span <= 0:
        return None

    stop_buffer = max(span * 0.05, entry * 0.001)

    if side == "LONG":
        stop = support - stop_buffer
        tp1 = entry + span * 0.25
        tp2 = entry + span * 0.50
        tp3 = entry + span * 0.90
    elif side == "SHORT":
        stop = resistance + stop_buffer
        tp1 = entry - span * 0.25
        tp2 = entry - span * 0.50
        tp3 = entry - span * 0.90
    else:
        return None

    rr1 = reward_risk(side, entry, stop, tp1)
    rr2 = reward_risk(side, entry, stop, tp2)
    rr3 = reward_risk(side, entry, stop, tp3)

    return {
        "side": side,
        "entry": entry,
        "sl": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rr1": rr1,
        "rr2": rr2,
        "rr3": rr3,
        "weighted_rr": weighted_rr(rr1, rr2, rr3),
    }


def _momentum_matches_side(side: str, stoch: dict[str, float] | None) -> bool:
    if not stoch:
        return False

    k = stoch.get("k")
    d = stoch.get("d")
    if k is None or d is None:
        return False

    if side == "LONG":
        return k <= 35.0 and k >= d
    if side == "SHORT":
        return k >= 65.0 and k <= d
    return False


def _derive_signal(
    price: float,
    support: float,
    resistance: float,
    position_pct: float,
    settings: Settings,
    volume_1h_relative: float | None,
    stoch_rsi_1h: dict[str, float] | None,
    volume_confirmation_threshold: float | None = None,
) -> tuple[dict[str, Any], dict[str, float | str] | None]:
    side = _derive_potential_side(position_pct)

    if resistance <= support:
        signal = {
            "side": "NO TRADE",
            "state": "NO_TRADE",
            "weighted_rr": None,
            "reason": "Invalid daily range (support >= resistance).",
        }
        return signal, None

    if side == "NEUTRAL":
        signal = {
            "side": side,
            "state": "NO_TRADE",
            "weighted_rr": None,
            "reason": "Price is in the neutral area of the active daily swing range.",
        }
        return signal, None

    candidate = _build_trade_candidate(side, price, support, resistance)
    weighted_rr_value = None if not candidate else float(candidate["weighted_rr"])

    vol_thresh = (
        float(volume_confirmation_threshold)
        if volume_confirmation_threshold is not None
        else getattr(settings, "volume_confirmation_threshold", 1.05)
    )
    has_volume = volume_1h_relative is not None and volume_1h_relative >= vol_thresh
    has_momentum = _momentum_matches_side(side, stoch_rsi_1h)

    if has_volume and has_momentum:
        state = "CONFIRMED"
        reason = "Volume and Stoch RSI 1H confirm the directional setup."
    else:
        state = "WATCH"
        reason = "Directional zone detected, waiting for 1H rejection/confirmation."

    if state == "CONFIRMED" and weighted_rr_value is not None:
        if weighted_rr_value >= settings.very_high_min_weighted_rr:
            state = "VERY_HIGH"
            reason = "Confirmed setup with weighted RR above VERY_HIGH threshold."
        elif weighted_rr_value >= settings.high_min_weighted_rr:
            state = "HIGH"
            reason = "Confirmed setup with weighted RR above HIGH threshold."

    signal = {
        "side": side,
        "state": state,
        "weighted_rr": None if weighted_rr_value is None else round(weighted_rr_value, 3),
        "reason": reason,
    }
    return signal, candidate


def _build_trade_plan(
    signal_state: str,
    candidate: dict[str, float | str],
    settings: Settings,
) -> tuple[dict[str, Any] | None, str | None]:
    side = str(candidate["side"])
    entry = float(candidate["entry"])
    sl = float(candidate["sl"])
    tp1 = float(candidate["tp1"])
    tp2 = float(candidate["tp2"])
    tp3 = float(candidate["tp3"])

    is_valid, topo_err = validate_trade_plan_topology(
        side=side,
        entry=entry,
        stop=sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
    )
    if not is_valid:
        return None, topo_err

    try:
        sizing = recommend_sizing(entry, sl, signal_state, settings, side=side)
    except NoValidSizingError as exc:
        return None, str(exc.reason)
    except Exception:
        return None, "TRADE_PLAN_INVALID"

    plan = {
        "side": side,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "tp3": round(tp3, 2),
        "rr1": round(float(candidate["rr1"]), 3),
        "rr2": round(float(candidate["rr2"]), 3),
        "rr3": round(float(candidate["rr3"]), 3),
        "weighted_rr": round(float(candidate["weighted_rr"]), 3),
        "margin_usd": float(sizing["margin_usd"]),
        "leverage": int(sizing["leverage"]),
        "notional_usd": float(sizing["notional_usd"]),
        "expected_r": None,
    }
    return plan, None


def _prepare_swing_inputs(
    *,
    daily_candles: list[Candle],
    daily_warmup_candles: list[Candle] | None,
    daily_candles_used: int | None,
    settings: Settings,
) -> tuple[list[Candle], list[Candle], int]:
    if daily_warmup_candles is not None:
        analysis_sessions = int(daily_candles_used if daily_candles_used is not None else len(daily_candles))
        analysis = list(daily_candles[-analysis_sessions:]) if analysis_sessions > 0 else []
        warmup_count = max(0, settings.swing_sma_period - 1)
        warmup = list(daily_warmup_candles[-warmup_count:]) if warmup_count else []
        return warmup, analysis, analysis_sessions

    analysis_sessions = int(daily_candles_used if daily_candles_used is not None else len(daily_candles))
    warmup, analysis = split_daily_candles_for_swing(
        closed_candles=list(daily_candles),
        analysis_sessions=analysis_sessions,
        sma_period=settings.swing_sma_period,
        strict=False,
    )
    return warmup, analysis, analysis_sessions


def build_dashboard_state(
    *,
    price: float,
    daily_candles: list[Candle],
    hourly_candles: list[Candle],
    settings: Settings,
    daily_warmup_candles: list[Candle] | None = None,
    daily_candles_used: int | None = None,
    backtest_candles_used: int | None = None,
    refresh_interval_seconds: int = 300,
    now: datetime | None = None,
    volume_1h_relative: float | None = None,
    stoch_rsi_1h: dict[str, float] | None = None,
    lookback_days: int | None = None,
    pivot_left: int | None = None,
    pivot_right: int | None = None,
    min_confirmations: int | None = None,
    cluster_tolerance_pct: float | None = None,
    sma20_filter_pct: float | None = None,
    operational_range_pct: float | None = None,
    min_operational_range_pct: float | None = None,
    volume_baseline_period: int | None = None,
    volume_confirmation_threshold: float | None = None,
    setup_context_manager: SetupContextManager | None = None,
    setup_context: SetupContext | None = None,
) -> dict[str, Any]:
    effective_lookback = int(
        lookback_days if lookback_days is not None else (daily_candles_used if daily_candles_used is not None else len(daily_candles))
    )
    warmup, analysis_candles, used_candles = _prepare_swing_inputs(
        daily_candles=daily_candles,
        daily_warmup_candles=daily_warmup_candles,
        daily_candles_used=effective_lookback,
        settings=settings,
    )

    effective_left = int(pivot_left if pivot_left is not None else settings.swing_left)
    effective_right = int(pivot_right if pivot_right is not None else settings.swing_right)
    effective_min_conf = int(min_confirmations if min_confirmations is not None else 2)
    effective_op_range_pct = float(operational_range_pct) if operational_range_pct is not None else None
    effective_min_op_range_pct = (
        float(min_operational_range_pct)
        if min_operational_range_pct is not None
        else float(getattr(settings, "min_operational_range_pct", 0.0))
    )
    effective_vol_period = int(
        volume_baseline_period if volume_baseline_period is not None else settings.volume_baseline_period
    )
    effective_vol_thresh = float(
        volume_confirmation_threshold
        if volume_confirmation_threshold is not None
        else getattr(settings, "volume_confirmation_threshold", 1.05)
    )

    raw_cluster_tol = cluster_tolerance_pct if cluster_tolerance_pct is not None else (settings.swing_cluster_tolerance_pct * 100.0)
    effective_cluster_tol_frac = raw_cluster_tol / 100.0 if raw_cluster_tol > 0.5 else raw_cluster_tol

    raw_sma_filter = sma20_filter_pct if sma20_filter_pct is not None else (settings.swing_sma_max_distance_pct * 100.0)
    effective_sma_filter_frac = raw_sma_filter / 100.0 if raw_sma_filter > 0.5 else raw_sma_filter

    swing_result = compute_swing_range_v2(
        analysis_candles=analysis_candles,
        warmup_candles=warmup,
        price=price,
        left=effective_left,
        right=effective_right,
        sma_period=settings.swing_sma_period,
        sma_max_distance_pct=effective_sma_filter_frac,
        cluster_tolerance_pct=effective_cluster_tol_frac,
        min_confirmations=effective_min_conf,
    )

    structural_support = swing_result.support
    structural_resistance = swing_result.resistance

    if structural_support >= structural_resistance and analysis_candles:
        structural_support = min(candle.low for candle in analysis_candles)
        structural_resistance = max(candle.high for candle in analysis_candles)
        if structural_support >= structural_resistance:
            structural_resistance = structural_support + max(1.0, abs(structural_support) * 0.001)

    operational_range = derive_operational_range(
        current_price=price,
        swing_result=swing_result,
        operational_range_pct=effective_op_range_pct,
        min_operational_range_pct=effective_min_op_range_pct,
        min_confirmations=effective_min_conf,
    )

    trade_diagnostics = build_trade_diagnostics(
        swing_result=swing_result,
        settings=settings,
        daily_candles_used=used_candles,
        sma_period=settings.swing_sma_period,
        sma_max_distance_pct=round(effective_sma_filter_frac * 100.0, 4),
        cluster_tolerance_pct=round(effective_cluster_tol_frac * 100.0, 4),
    )

    if volume_1h_relative is None:
        volume_1h_relative = relative_volume(hourly_candles, effective_vol_period)

    if stoch_rsi_1h is None:
        stoch_rsi_1h = stochastic_rsi(
            [c.close for c in hourly_candles],
            settings.rsi_period,
            settings.stoch_rsi_period,
            settings.stoch_k,
            settings.stoch_d,
        )

    stoch_market = None
    if stoch_rsi_1h is not None:
        stoch_market = {
            "k": round(float(stoch_rsi_1h.get("k", 0.0)), 2),
            "d": round(float(stoch_rsi_1h.get("d", 0.0)), 2),
            "state": classify_stoch_state(stoch_rsi_1h),
        }

    volume_24h_hourly = compute_volume_24h_hourly(hourly_candles)
    timestamp = (now or datetime.now(timezone.utc)).isoformat()

    # Active setup context lookup & lifecycle
    active_setup = setup_context or (setup_context_manager.current_setup if setup_context_manager else None)
    was_invalidated = False
    setup_invalidated_opposite_side = False
    sizing_error: str | None = None
    plan_error: str | None = None

    if active_setup is not None:
        # Check invalidation: price breaks beyond frozen setup boundaries
        if active_setup.side == "LONG" and price < active_setup.support:
            was_invalidated = True
        elif active_setup.side == "SHORT" and price > active_setup.resistance:
            was_invalidated = True

        if was_invalidated:
            cleared = True
            if setup_context_manager is not None:
                cleared = setup_context_manager.clear(reason="BOUNDARY_BREACH", now_iso=timestamp)
            if cleared:
                active_setup = None
                position_pct = compute_position_pct(price, structural_support, structural_resistance) if structural_support < structural_resistance else 0.0
                signal = {
                    "side": "NO TRADE",
                    "state": "NO_TRADE",
                    "weighted_rr": None,
                    "reason": "Active setup was invalidated (price broke beyond frozen level).",
                }
                candidate = None
                trade_plan = None
                trade_window_open = False
            else:
                signal = {
                    "side": "NO TRADE",
                    "state": "NO_TRADE",
                    "weighted_rr": None,
                    "reason": "Active setup invalidation failed to persist safely.",
                }
                candidate = None
                trade_plan = None
                trade_window_open = False
        else:
            # Active setup: downstream trade path uses FROZEN boundaries
            effective_support = active_setup.support
            effective_resistance = active_setup.resistance
            position_pct = compute_position_pct(price, effective_support, effective_resistance)

            signal, candidate = _derive_signal(
                price=price,
                support=effective_support,
                resistance=effective_resistance,
                position_pct=position_pct,
                settings=settings,
                volume_1h_relative=volume_1h_relative,
                stoch_rsi_1h=stoch_rsi_1h,
                volume_confirmation_threshold=effective_vol_thresh,
            )

            # Check directional mismatch or opposite side condition (REQ-V3-TRD-004, REQ-V3-TRD-005)
            if candidate is not None and candidate.get("side") and candidate["side"] != active_setup.side:
                setup_invalidated_opposite_side = True
                cleared = True
                if setup_context_manager is not None:
                    cleared = setup_context_manager.clear(reason="OPPOSITE_SIDE", now_iso=timestamp)
                if cleared:
                    active_setup = None
                    signal = {
                        "side": "NO TRADE",
                        "state": "NO_TRADE",
                        "weighted_rr": None,
                        "reason": "Active setup was invalidated due to opposite directional conditions.",
                    }
                    candidate = None
                    trade_plan = None
                    trade_window_open = False
                else:
                    signal = {
                        "side": "NO TRADE",
                        "state": "NO_TRADE",
                        "weighted_rr": None,
                        "reason": "Active setup invalidation failed to persist safely.",
                    }
                    candidate = None
                    trade_plan = None
                    trade_window_open = False
            else:
                trade_window_open = trade_window_open_for_state(signal["state"])
                if trade_window_open and candidate:
                    trade_plan, plan_error = _build_trade_plan(signal["state"], candidate, settings)
                    sizing_error = plan_error
                else:
                    trade_plan, plan_error = None, None
                trade_window_open = trade_window_open and trade_plan is not None
    else:
        # No active setup: evaluate from live operational levels
        if operational_range.is_valid and operational_range.support.price is not None and operational_range.resistance.price is not None:
            effective_support = operational_range.support.price
            effective_resistance = operational_range.resistance.price
            position_pct = compute_position_pct(price, effective_support, effective_resistance)

            signal, candidate = _derive_signal(
                price=price,
                support=effective_support,
                resistance=effective_resistance,
                position_pct=position_pct,
                settings=settings,
                volume_1h_relative=volume_1h_relative,
                stoch_rsi_1h=stoch_rsi_1h,
                volume_confirmation_threshold=effective_vol_thresh,
            )

            # Setup creation trigger: ONLY on genuine entry into WATCH
            if signal["state"] == "WATCH" and signal["side"] in {"LONG", "SHORT"}:
                origin_cfg = {
                    "coin": getattr(settings, "coin", "BTC"),
                    "lookback_days": effective_lookback,
                    "pivot_left": effective_left,
                    "pivot_right": effective_right,
                    "min_confirmations": effective_min_conf,
                    "cluster_tolerance_pct": round(effective_cluster_tol_frac * 100.0, 4),
                    "sma20_filter_pct": round(effective_sma_filter_frac * 100.0, 4),
                    "operational_range_pct": round(effective_op_range_pct, 4) if effective_op_range_pct is not None else 10.0,
                    "min_operational_range_pct": round(effective_min_op_range_pct, 4),
                    "volume_baseline_period": effective_vol_period,
                    "volume_confirmation_threshold": effective_vol_thresh,
                }
                if setup_context_manager is not None:
                    active_setup = setup_context_manager.update(
                        price=price,
                        operational_support=effective_support,
                        operational_resistance=effective_resistance,
                        operational_valid=True,
                        signal_state=signal["state"],
                        signal_side=signal["side"],
                        position_pct=position_pct,
                        config=origin_cfg,
                        now_iso=timestamp,
                    )
            else:
                active_setup = None

            if setup_context_manager is not None:
                # Under runtime manager with no active setup, trade window remains closed
                trade_window_open = False
                trade_plan = None
            else:
                trade_window_open = trade_window_open_for_state(signal["state"])
                if trade_window_open and candidate:
                    trade_plan, plan_error = _build_trade_plan(signal["state"], candidate, settings)
                    sizing_error = plan_error
                else:
                    trade_plan, plan_error = None, None
                trade_window_open = trade_window_open and trade_plan is not None
        else:
            position_pct = compute_position_pct(price, structural_support, structural_resistance) if structural_support < structural_resistance else 0.0
            signal = {
                "side": "NO TRADE",
                "state": "NO_TRADE",
                "weighted_rr": None,
                "reason": "Operational level is invalid or outside configured operational range.",
            }
            candidate = None
            trade_plan = None
            trade_window_open = False
            active_setup = None

    potential_trade_plan: dict[str, Any] | None = None
    if signal.get("state") != "NO_TRADE" and candidate is not None:
        if trade_plan is not None:
            potential_trade_plan = trade_plan
        else:
            computed_potential, _ = _build_trade_plan(str(signal.get("state")), candidate, settings)
            potential_trade_plan = computed_potential

    weighted_rr_val = float(candidate["weighted_rr"]) if (candidate and candidate.get("weighted_rr") is not None) else None
    block_reason = derive_block_reason(
        trade_window_open=trade_window_open,
        price=price,
        operational_range=operational_range,
        active_setup=active_setup,
        was_invalidated=was_invalidated,
        signal_state=str(signal.get("state")),
        weighted_rr=weighted_rr_val,
        candidate=candidate,
        trade_plan=trade_plan,
        sizing_error=sizing_error,
        min_weighted_rr=settings.high_min_weighted_rr,
        plan_error=plan_error,
        setup_invalidated_opposite_side=setup_invalidated_opposite_side,
    )

    is_operational_full = (
        operational_range.is_valid
        and operational_range.support.valid
        and operational_range.support.price is not None
        and operational_range.resistance.valid
        and operational_range.resistance.price is not None
        and operational_range.support.price < operational_range.resistance.price
    )

    if is_operational_full:
        range_display_type = "operational"
        display_support = operational_range.support.price
        display_resistance = operational_range.resistance.price
    else:
        range_display_type = "structural"
        display_support = structural_support
        display_resistance = structural_resistance

    return {
        "timestamp": timestamp,
        "algorithm_version": ALGORITHM_VERSION,
        "coin": settings.coin,
        "refresh_interval_seconds": refresh_interval_seconds,
        "market": {
            "price": round(price, 2) if math.isfinite(price) else None,
            "volume_24h_hourly": volume_24h_hourly,
            "stoch_rsi_1h": stoch_market,
        },
        "swing_range": {
            "display_type": range_display_type,
            "support": round(display_support, 2),
            "resistance": round(display_resistance, 2),
            "position_pct": round(position_pct, 2) if position_pct is not None else None,
            "daily_candles_used": used_candles,
            "structural_support": round(structural_support, 2),
            "structural_resistance": round(structural_resistance, 2),
            "operational_support": operational_range.support.price,
            "operational_resistance": operational_range.resistance.price,
            "operational_support_source": operational_range.support.source,
            "operational_resistance_source": operational_range.resistance.source,
            "operational_support_confirmations": operational_range.support.confirmations,
            "operational_resistance_confirmations": operational_range.resistance.confirmations,
            "operational_support_distance_pct": operational_range.support.distance_pct,
            "operational_resistance_distance_pct": operational_range.resistance.distance_pct,
            "operational_support_valid": operational_range.support.valid,
            "operational_resistance_valid": operational_range.resistance.valid,
            "operational_valid": operational_range.is_valid,
            "range_width": round(operational_range.range_width, 2),
            "range_width_pct": round(operational_range.range_width_pct, 4),
            "too_narrow": operational_range.too_narrow,
            "min_operational_range_pct": round(effective_min_op_range_pct, 4),
        },
        "operational_range": {
            "support": operational_range.support.price,
            "resistance": operational_range.resistance.price,
            "support_source": operational_range.support.source,
            "resistance_source": operational_range.resistance.source,
            "support_confirmations": operational_range.support.confirmations,
            "resistance_confirmations": operational_range.resistance.confirmations,
            "support_distance_pct": operational_range.support.distance_pct,
            "resistance_distance_pct": operational_range.resistance.distance_pct,
            "support_valid": operational_range.support.valid,
            "resistance_valid": operational_range.resistance.valid,
            "is_valid": operational_range.is_valid,
            "operational_range_pct": effective_op_range_pct,
            "range_width": round(operational_range.range_width, 2),
            "range_width_pct": round(operational_range.range_width_pct, 4),
            "too_narrow": operational_range.too_narrow,
            "min_operational_range_pct": round(effective_min_op_range_pct, 4),
        },
        "setup_context": active_setup.to_dict() if active_setup is not None else {"active": False},
        "signal": {
            **signal,
            "metrics": {
                "volume_1h_relative": None if volume_1h_relative is None else round(volume_1h_relative, 3),
                "stoch_rsi_1h": stoch_market,
            },
        },
        "statistics": {
            "backtest_candles_used": backtest_candles_used,
        },
        "trade_diagnostics": trade_diagnostics,
        "trade_window_open": trade_window_open,
        "block_reason": block_reason,
        "trade_plan": trade_plan,
        "potential_trade_plan": potential_trade_plan,
    }
