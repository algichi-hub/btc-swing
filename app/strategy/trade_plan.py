from __future__ import annotations

INVALID_LONG_STOP_GEOMETRY = "INVALID_LONG_STOP_GEOMETRY"

INVALID_SHORT_STOP_GEOMETRY = "INVALID_SHORT_STOP_GEOMETRY"
INVALID_TP_ORDER = "INVALID_TP_ORDER"


def validate_trade_plan_topology(
    side: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    tp3: float,
) -> tuple[bool, str | None]:
    """Validate strict directional topology for trade plans (REQ-V3-TRD-001 & REQ-V3-TRD-002)."""
    norm_side = side.upper()
    if norm_side == "LONG":
        if stop >= entry:
            return False, INVALID_LONG_STOP_GEOMETRY
        if not (entry < tp1 < tp2 < tp3):
            return False, INVALID_TP_ORDER
        return True, None
    elif norm_side == "SHORT":
        if entry >= stop:
            return False, INVALID_SHORT_STOP_GEOMETRY
        if not (tp3 < tp2 < tp1 < entry):
            return False, INVALID_TP_ORDER
        return True, None
    return False, "TRADE_PLAN_INVALID"


def reward_risk(side: str, entry: float, stop: float, target: float) -> float:
    """Calculate reward/risk with directional validation (REQ-V3-TRD-006)."""
    norm_side = side.upper()
    if norm_side == "LONG":
        risk = entry - stop
        if risk <= 0:
            return 0.0
        reward = target - entry
        if reward <= 0:
            return 0.0
        return reward / risk
    elif norm_side == "SHORT":
        risk = stop - entry
        if risk <= 0:
            return 0.0
        reward = entry - target
        if reward <= 0:
            return 0.0
        return reward / risk
    return 0.0


def weighted_rr(rr1: float, rr2: float, rr3: float, allocations=(0.30, 0.30, 0.40)) -> float:
    return rr1 * allocations[0] + rr2 * allocations[1] + rr3 * allocations[2]
