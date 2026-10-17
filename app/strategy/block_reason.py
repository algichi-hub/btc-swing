from __future__ import annotations

import math
from typing import Any

from app.strategy.setup_context import SetupContext
from app.strategy.swing_range import OperationalRangeResult

NO_TECHNICAL_SETUP = "NO_TECHNICAL_SETUP"
STATE_BELOW_HIGH = "STATE_BELOW_HIGH"
REJECTION_NOT_CONFIRMED = "REJECTION_NOT_CONFIRMED"
CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
NO_OPERATIONAL_SUPPORT = "NO_OPERATIONAL_SUPPORT"
NO_OPERATIONAL_RESISTANCE = "NO_OPERATIONAL_RESISTANCE"
NO_VALID_OPERATIONAL_RANGE = "NO_VALID_OPERATIONAL_RANGE"
WEIGHTED_RR_TOO_LOW = "WEIGHTED_RR_TOO_LOW"
TRADE_PLAN_INVALID = "TRADE_PLAN_INVALID"
NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS = "NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS"
MAX_TRADE_LOSS_EXCEEDED = "MAX_TRADE_LOSS_EXCEEDED"
MAX_MARGIN_LOSS_EXCEEDED = "MAX_MARGIN_LOSS_EXCEEDED"
SETUP_EXPIRED = "SETUP_EXPIRED"
SETUP_INVALIDATED = "SETUP_INVALIDATED"
BREAKOUT = "BREAKOUT"
UNKNOWN = "UNKNOWN"

# V3 Canonical Block Reasons
INVALID_LONG_STOP_GEOMETRY = "INVALID_LONG_STOP_GEOMETRY"
INVALID_SHORT_STOP_GEOMETRY = "INVALID_SHORT_STOP_GEOMETRY"
SETUP_TRADE_SIDE_MISMATCH = "SETUP_TRADE_SIDE_MISMATCH"
SETUP_INVALIDATED_OPPOSITE_SIDE = "SETUP_INVALIDATED_OPPOSITE_SIDE"
INVALID_TP_ORDER = "INVALID_TP_ORDER"
OPERATIONAL_RANGE_TOO_NARROW = "OPERATIONAL_RANGE_TOO_NARROW"

CANONICAL_BLOCK_REASONS = {
    NO_TECHNICAL_SETUP,
    STATE_BELOW_HIGH,
    REJECTION_NOT_CONFIRMED,
    CONFIRMATION_PENDING,
    NO_OPERATIONAL_SUPPORT,
    NO_OPERATIONAL_RESISTANCE,
    NO_VALID_OPERATIONAL_RANGE,
    WEIGHTED_RR_TOO_LOW,
    TRADE_PLAN_INVALID,
    NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS,
    MAX_TRADE_LOSS_EXCEEDED,
    MAX_MARGIN_LOSS_EXCEEDED,
    SETUP_EXPIRED,
    SETUP_INVALIDATED,
    BREAKOUT,
    UNKNOWN,
    INVALID_LONG_STOP_GEOMETRY,
    INVALID_SHORT_STOP_GEOMETRY,
    SETUP_TRADE_SIDE_MISMATCH,
    SETUP_INVALIDATED_OPPOSITE_SIDE,
    INVALID_TP_ORDER,
    OPERATIONAL_RANGE_TOO_NARROW,
}


def derive_block_reason(
    *,
    trade_window_open: bool,
    price: float,
    operational_range: OperationalRangeResult,
    active_setup: SetupContext | None,
    was_invalidated: bool,
    signal_state: str,
    weighted_rr: float | None,
    candidate: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    sizing_error: str | None = None,
    min_weighted_rr: float = 1.80,
    plan_error: str | None = None,
    setup_invalidated_opposite_side: bool = False,
) -> str | None:
    """Derive the deterministic canonical block_reason for non-actionable cycles."""
    if trade_window_open:
        return None

    # Priority 1: Invalidation events in current cycle
    if setup_invalidated_opposite_side:
        return SETUP_INVALIDATED_OPPOSITE_SIDE

    if was_invalidated:
        return SETUP_INVALIDATED

    # Priority 2: Operational range width check (REQ-V3-RNG-006)
    if getattr(operational_range, "too_narrow", False):
        return OPERATIONAL_RANGE_TOO_NARROW

    # Priority 3: Malformed or missing operational levels
    if not math.isfinite(price) or price <= 0:
        return NO_VALID_OPERATIONAL_RANGE

    if not operational_range.support.valid or operational_range.support.price is None:
        return NO_OPERATIONAL_SUPPORT

    if not operational_range.resistance.valid or operational_range.resistance.price is None:
        return NO_OPERATIONAL_RESISTANCE

    if not operational_range.is_valid or operational_range.support.price >= operational_range.resistance.price:
        return NO_VALID_OPERATIONAL_RANGE

    # Priority 4: Active Setup Presence
    if active_setup is None:
        return NO_TECHNICAL_SETUP

    # Priority 5: Setup and Candidate side mismatch (REQ-V3-TRD-004)
    if candidate is not None and candidate.get("side") and active_setup.side != candidate.get("side"):
        return SETUP_TRADE_SIDE_MISMATCH

    # Priority 6: Specific plan errors (topology or sizing) (REQ-V3-TRD-008)
    if plan_error in {
        INVALID_LONG_STOP_GEOMETRY,
        INVALID_SHORT_STOP_GEOMETRY,
        INVALID_TP_ORDER,
        SETUP_TRADE_SIDE_MISMATCH,
    }:
        return plan_error

    if sizing_error in {
        MAX_TRADE_LOSS_EXCEEDED,
        MAX_MARGIN_LOSS_EXCEEDED,
        NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS,
        INVALID_LONG_STOP_GEOMETRY,
        INVALID_SHORT_STOP_GEOMETRY,
    }:
        return sizing_error

    if signal_state in {"HIGH", "VERY_HIGH"} and candidate is not None and trade_plan is None:
        if plan_error:
            return plan_error
        return TRADE_PLAN_INVALID

    # Priority 7: Confirmation / Progression
    if signal_state == "WATCH":
        return CONFIRMATION_PENDING

    if signal_state == "CONFIRMED":
        if weighted_rr is not None and weighted_rr < min_weighted_rr:
            return WEIGHTED_RR_TOO_LOW
        return STATE_BELOW_HIGH

    if signal_state == "NO_TRADE":
        return NO_TECHNICAL_SETUP

    if weighted_rr is not None and weighted_rr < min_weighted_rr:
        return WEIGHTED_RR_TOO_LOW

    if signal_state not in {"HIGH", "VERY_HIGH"}:
        return STATE_BELOW_HIGH

    return UNKNOWN
