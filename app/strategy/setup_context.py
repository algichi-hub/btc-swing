from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any
import uuid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetupContext:
    active: bool
    setup_id: str
    side: str
    started_at: str
    support: float
    resistance: float
    midpoint: float
    range_width: float
    origin_state: str
    origin_price: float
    origin_range_position_pct: float
    origin_rejection_level: float
    origin_config: dict[str, Any]
    range_width_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "setup_id": self.setup_id,
            "side": self.side,
            "started_at": self.started_at,
            "support": round(self.support, 2),
            "resistance": round(self.resistance, 2),
            "midpoint": round(self.midpoint, 2),
            "range_width": round(self.range_width, 2),
            "range_width_pct": round(self.range_width_pct, 4),
            "origin_state": self.origin_state,
            "origin_price": round(self.origin_price, 2),
            "origin_range_position_pct": round(self.origin_range_position_pct, 2),
            "origin_rejection_level": round(self.origin_rejection_level, 2),
            "origin_config": dict(self.origin_config),
        }

    @classmethod
    def from_opportunity(cls, opp: dict[str, Any]) -> SetupContext:
        support = float(opp["support"])
        resistance = float(opp["resistance"])
        origin_price = float(opp["origin_price"])
        side = str(opp["side"])
        midpoint = (support + resistance) / 2.0
        range_width = resistance - support
        range_width_pct = (range_width / midpoint * 100.0) if midpoint > 0 else 0.0
        rejection_level = support if side == "LONG" else resistance
        pos_pct = (
            round(((origin_price - support) / range_width) * 100.0, 2)
            if range_width > 0
            else 0.0
        )
        return cls(
            active=True,
            setup_id=str(opp["setup_id"]),
            side=side,
            started_at=str(opp["created_at"]),
            support=support,
            resistance=resistance,
            midpoint=midpoint,
            range_width=range_width,
            range_width_pct=range_width_pct,
            origin_state="WATCH",
            origin_price=origin_price,
            origin_range_position_pct=pos_pct,
            origin_rejection_level=rejection_level,
            origin_config={"coin": opp.get("coin", "BTC")},
        )


class SetupContextManager:
    """In-memory process runtime manager for active technical setup context."""

    def __init__(self, repository: Any = None) -> None:
        self._current_setup: SetupContext | None = None
        self.repository = repository

    @property
    def current_setup(self) -> SetupContext | None:
        return self._current_setup

    def restore_setup(self, setup: SetupContext) -> None:
        self._current_setup = setup

    def clear(self, reason: str = "MANUAL_CLEAR", now_iso: str | None = None) -> bool:
        """
        Fail-closed invalidation:
        Only clears _current_setup if SQLite persistence succeeds.
        If mark_opportunity_invalidated fails, retains _current_setup protected and returns False.
        """
        if self._current_setup is not None and self.repository is not None:
            try:
                ok = self.repository.mark_opportunity_invalidated(
                    self._current_setup.setup_id,
                    reason=reason,
                    invalidated_at=now_iso,
                )
                if not ok:
                    opp = self.repository.get_opportunity(self._current_setup.setup_id)
                    if opp and opp.get("status") != "INVALIDATED":
                        logger.error(
                            "Failed to mark opportunity %s invalidated (status=%s)",
                            self._current_setup.setup_id,
                            opp.get("status"),
                        )
                        return False
            except Exception as exc:
                logger.exception(
                    "Persistence error invalidating opportunity %s: %s",
                    self._current_setup.setup_id,
                    exc,
                )
                return False

        self._current_setup = None
        return True

    def update(
        self,
        *,
        price: float,
        operational_support: float | None,
        operational_resistance: float | None,
        operational_valid: bool,
        signal_state: str,
        signal_side: str,
        position_pct: float | None,
        config: dict[str, Any],
        now_iso: str,
    ) -> SetupContext | None:
        # Check invalidation if an active setup exists
        if self._current_setup is not None:
            setup = self._current_setup
            # Explicit invalidation: price breaks beyond frozen boundaries
            if setup.side == "LONG" and price < setup.support:
                if not self.clear(reason="BOUNDARY_BREACH", now_iso=now_iso):
                    return self._current_setup
                return None
            if setup.side == "SHORT" and price > setup.resistance:
                if not self.clear(reason="BOUNDARY_BREACH", now_iso=now_iso):
                    return self._current_setup
                return None

            # Opposite side condition check (REQ-V3-TRD-005)
            if signal_side in {"LONG", "SHORT"} and signal_side != setup.side:
                if not self.clear(reason="OPPOSITE_SIDE", now_iso=now_iso):
                    return self._current_setup
                return None
            
            return self._current_setup

        # No active setup: check entry condition (requires genuine WATCH)
        if not operational_valid or operational_support is None or operational_resistance is None:
            return None

        if signal_state != "WATCH" or signal_side not in {"LONG", "SHORT"}:
            return None

        if not (math.isfinite(price) and math.isfinite(operational_support) and math.isfinite(operational_resistance)):
            return None

        if price <= 0 or operational_support >= operational_resistance:
            return None

        if position_pct is None or not math.isfinite(position_pct):
            return None

        midpoint = (operational_support + operational_resistance) / 2.0
        range_width = operational_resistance - operational_support
        range_width_pct = (range_width / midpoint * 100.0) if midpoint > 0 else 0.0
        rejection_level = operational_support if signal_side == "LONG" else operational_resistance

        new_setup = SetupContext(
            active=True,
            setup_id=str(uuid.uuid4()),
            side=signal_side,
            started_at=now_iso,
            support=operational_support,
            resistance=operational_resistance,
            midpoint=midpoint,
            range_width=range_width,
            range_width_pct=range_width_pct,
            origin_state="WATCH",
            origin_price=price,
            origin_range_position_pct=position_pct,
            origin_rejection_level=rejection_level,
            origin_config=dict(config),
        )

        if self.repository is not None:
            try:
                coin = str(config.get("coin") or "BTC")
                self.repository.create_opportunity(
                    setup_id=new_setup.setup_id,
                    coin=coin,
                    side=signal_side,
                    support=operational_support,
                    resistance=operational_resistance,
                    origin_price=price,
                    created_at=now_iso,
                )
            except Exception as exc:
                logger.exception(
                    "Persistence error creating opportunity %s: %s",
                    new_setup.setup_id,
                    exc,
                )
                # Fail-closed: do NOT activate RAM setup if SQLite persistence fails
                self._current_setup = None
                return None

        self._current_setup = new_setup
        return new_setup
