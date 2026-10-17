from __future__ import annotations

from app.config import Settings


MAX_TRADE_LOSS_EXCEEDED = "MAX_TRADE_LOSS_EXCEEDED"
MAX_MARGIN_LOSS_EXCEEDED = "MAX_MARGIN_LOSS_EXCEEDED"
NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS = "NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS"


class NoValidSizingError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def recommend_sizing(
    entry: float,
    stop: float,
    signal_state: str,
    settings: Settings,
    side: str | None = None,
) -> dict[str, float | int]:
    if entry <= 0:
        raise NoValidSizingError(NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS)

    if side is not None:
        norm_side = side.upper()
        if norm_side == "LONG":
            if stop >= entry:
                raise NoValidSizingError("INVALID_LONG_STOP_GEOMETRY")
            stop_distance = entry - stop
        elif norm_side == "SHORT":
            if stop <= entry:
                raise NoValidSizingError("INVALID_SHORT_STOP_GEOMETRY")
            stop_distance = stop - entry
        else:
            stop_distance = abs(entry - stop)
    else:
        if entry == stop:
            raise NoValidSizingError(NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS)
        stop_distance = abs(entry - stop)

    stop_pct = stop_distance / entry


    effective_min_margin = max(50.0, float(settings.min_margin_usd))
    effective_max_margin = min(200.0, float(settings.max_margin_usd))
    if effective_min_margin > effective_max_margin:
        effective_min_margin, effective_max_margin = 50.0, 200.0

    base_margin = min(effective_max_margin, max(effective_min_margin, float(settings.base_margin_usd)))
    margin = base_margin
    if signal_state == "VERY_HIGH":
        margin = min(effective_max_margin, max(base_margin, 150.0))
    elif signal_state == "HIGH":
        margin = base_margin

    configured_min_leverage = int(settings.min_leverage)
    configured_max_leverage = int(settings.max_leverage)
    effective_min_leverage = max(5, configured_min_leverage)
    effective_max_leverage = min(25, configured_max_leverage)
    if effective_min_leverage > effective_max_leverage:
        effective_min_leverage, effective_max_leverage = 5, 25

    leverage: int | None = None
    for candidate in range(effective_max_leverage, effective_min_leverage - 1, -1):
        margin_loss_pct = stop_pct * candidate
        loss_usd = margin * margin_loss_pct
        if margin_loss_pct <= settings.max_margin_loss_pct and loss_usd <= settings.max_trade_loss_usd:
            leverage = candidate
            break

    if leverage is None:
        raise NoValidSizingError(NO_VALID_SIZING_UNDER_RISK_CONSTRAINTS)

    return {
        "margin_usd": round(margin, 2),
        "leverage": leverage,
        "notional_usd": round(margin * leverage, 2),
        "stop_distance_pct": round(stop_pct * 100, 4),
        "estimated_loss_at_stop_usd": round(margin * stop_pct * leverage, 2),
    }
