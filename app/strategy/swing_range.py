from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import mean
from typing import Literal

from app.models import Candle

PivotKind = Literal["LOW", "HIGH"]
OperationalSource = Literal["cluster", "pivot_fallback", "none"]


@dataclass(frozen=True)
class OperationalLevel:
    price: float | None
    source: OperationalSource
    confirmations: int
    distance_pct: float | None
    valid: bool


@dataclass(frozen=True)
class OperationalRangeResult:
    support: OperationalLevel
    resistance: OperationalLevel
    operational_range_pct: float
    is_valid: bool
    range_width: float = 0.0
    range_width_pct: float = 0.0
    too_narrow: bool = False
    min_operational_range_pct: float = 0.0


@dataclass(frozen=True)
class RawPivot:
    kind: PivotKind
    price: float
    timestamp_ms: int
    candle_index: int


@dataclass(frozen=True)
class FilteredPivot:
    kind: PivotKind
    price: float
    timestamp_ms: int
    candle_index: int
    sma_value: float
    distance_pct: float


@dataclass(frozen=True)
class PivotCluster:
    center: float
    score: int
    pivots: tuple[FilteredPivot, ...]


@dataclass(frozen=True)
class SwingRangeV2Result:
    support: float
    resistance: float
    analysis_candles: tuple[Candle, ...]
    warmup_candles: tuple[Candle, ...]
    analysis_sma: tuple[float | None, ...]
    filtered_low_pivots: tuple[FilteredPivot, ...]
    filtered_high_pivots: tuple[FilteredPivot, ...]
    low_clusters: tuple[PivotCluster, ...]
    high_clusters: tuple[PivotCluster, ...]
    selected_support_cluster: PivotCluster | None
    selected_resistance_cluster: PivotCluster | None


def split_daily_candles_for_swing(
    *,
    closed_candles: list[Candle],
    analysis_sessions: int,
    sma_period: int,
    strict: bool,
) -> tuple[list[Candle], list[Candle]]:
    if analysis_sessions <= 0:
        raise ValueError("analysis_sessions must be greater than zero")
    if sma_period < 2:
        raise ValueError("sma_period must be at least 2")

    warmup_count = sma_period - 1
    required_closed = analysis_sessions + warmup_count

    if strict and len(closed_candles) < required_closed:
        raise ValueError(
            "Insufficient closed daily candles for swing analysis: "
            f"required at least {required_closed}, received {len(closed_candles)}"
        )

    if len(closed_candles) < analysis_sessions:
        raise ValueError(
            "Insufficient closed daily candles for analysis window: "
            f"required at least {analysis_sessions}, received {len(closed_candles)}"
        )

    if len(closed_candles) >= required_closed:
        selected = closed_candles[-required_closed:]
        return selected[:warmup_count], selected[warmup_count:]

    analysis_start = len(closed_candles) - analysis_sessions
    warmup_start = max(0, analysis_start - warmup_count)
    return closed_candles[warmup_start:analysis_start], closed_candles[analysis_start:]


def compute_swing_range_v2(
    *,
    analysis_candles: list[Candle],
    warmup_candles: list[Candle],
    price: float,
    left: int,
    right: int,
    sma_period: int,
    sma_max_distance_pct: float,
    cluster_tolerance_pct: float,
    min_confirmations: int = 2,
) -> SwingRangeV2Result:
    if not analysis_candles:
        raise ValueError("At least one analysis candle is required")
    if sma_period < 2:
        raise ValueError("sma_period must be at least 2")
    if sma_max_distance_pct <= 0:
        raise ValueError("sma_max_distance_pct must be greater than zero")
    if cluster_tolerance_pct <= 0:
        raise ValueError("cluster_tolerance_pct must be greater than zero")
    if min_confirmations < 1:
        raise ValueError("min_confirmations must be at least 1")

    left = max(1, left)
    right = max(1, right)

    effective_cluster_tol = cluster_tolerance_pct / 100.0 if cluster_tolerance_pct > 1.0 else cluster_tolerance_pct
    effective_sma_dist = sma_max_distance_pct / 100.0 if sma_max_distance_pct > 1.0 else sma_max_distance_pct

    combined_candles = [*warmup_candles, *analysis_candles]
    combined_sma = _sma_close_series(combined_candles, sma_period)
    warmup_count = len(warmup_candles)

    raw_low_pivots, raw_high_pivots = _confirmed_raw_pivots(analysis_candles, left, right)

    filtered_low_pivots = _filter_pivots_by_sma(
        pivots=raw_low_pivots,
        combined_sma=combined_sma,
        warmup_count=warmup_count,
        sma_max_distance_pct=effective_sma_dist,
    )
    filtered_high_pivots = _filter_pivots_by_sma(
        pivots=raw_high_pivots,
        combined_sma=combined_sma,
        warmup_count=warmup_count,
        sma_max_distance_pct=effective_sma_dist,
    )

    low_clusters = _build_clusters(filtered_low_pivots, effective_cluster_tol)
    high_clusters = _build_clusters(filtered_high_pivots, effective_cluster_tol)

    selected_support_cluster = _select_support_cluster(low_clusters, price, min_confirmations=min_confirmations)
    selected_resistance_cluster = _select_resistance_cluster(high_clusters, price, min_confirmations=min_confirmations)

    fallback_support = min(candle.low for candle in analysis_candles)
    fallback_resistance = max(candle.high for candle in analysis_candles)

    support = selected_support_cluster.center if selected_support_cluster is not None else fallback_support
    resistance = (
        selected_resistance_cluster.center if selected_resistance_cluster is not None else fallback_resistance
    )

    analysis_sma: list[float | None] = []
    for analysis_index in range(len(analysis_candles)):
        combined_index = warmup_count + analysis_index
        analysis_sma.append(combined_sma[combined_index] if combined_index < len(combined_sma) else None)

    return SwingRangeV2Result(
        support=support,
        resistance=resistance,
        analysis_candles=tuple(analysis_candles),
        warmup_candles=tuple(warmup_candles),
        analysis_sma=tuple(analysis_sma),
        filtered_low_pivots=tuple(filtered_low_pivots),
        filtered_high_pivots=tuple(filtered_high_pivots),
        low_clusters=tuple(low_clusters),
        high_clusters=tuple(high_clusters),
        selected_support_cluster=selected_support_cluster,
        selected_resistance_cluster=selected_resistance_cluster,
    )


def _confirmed_raw_pivots(candles: list[Candle], left: int, right: int) -> tuple[list[RawPivot], list[RawPivot]]:
    if not candles:
        return [], []

    low_pivots: list[RawPivot] = []
    high_pivots: list[RawPivot] = []

    for idx in range(left, len(candles) - right):
        window = candles[idx - left : idx + right + 1]
        current = candles[idx]

        if all(current.low <= row.low for row in window):
            low_pivots.append(
                RawPivot(
                    kind="LOW",
                    price=current.low,
                    timestamp_ms=current.open_time_ms,
                    candle_index=idx,
                )
            )

        if all(current.high >= row.high for row in window):
            high_pivots.append(
                RawPivot(
                    kind="HIGH",
                    price=current.high,
                    timestamp_ms=current.open_time_ms,
                    candle_index=idx,
                )
            )

    return low_pivots, high_pivots


def _sma_close_series(candles: list[Candle], period: int) -> list[float | None]:
    if period < 2:
        raise ValueError("period must be at least 2")

    result: list[float | None] = [None] * len(candles)
    for idx in range(period - 1, len(candles)):
        window = candles[idx - period + 1 : idx + 1]
        result[idx] = mean(candle.close for candle in window)
    return result


def _filter_pivots_by_sma(
    *,
    pivots: list[RawPivot],
    combined_sma: list[float | None],
    warmup_count: int,
    sma_max_distance_pct: float,
) -> list[FilteredPivot]:
    filtered: list[FilteredPivot] = []

    for pivot in pivots:
        combined_index = warmup_count + pivot.candle_index
        if combined_index < 0 or combined_index >= len(combined_sma):
            continue

        sma_value = combined_sma[combined_index]
        if sma_value is None or abs(sma_value) <= 1e-12:
            continue

        distance_pct = abs(pivot.price - sma_value) / abs(sma_value)
        if distance_pct <= sma_max_distance_pct + 1e-12:
            filtered.append(
                FilteredPivot(
                    kind=pivot.kind,
                    price=pivot.price,
                    timestamp_ms=pivot.timestamp_ms,
                    candle_index=pivot.candle_index,
                    sma_value=sma_value,
                    distance_pct=distance_pct,
                )
            )

    return filtered


def _build_clusters(pivots: list[FilteredPivot], tolerance_pct: float) -> list[PivotCluster]:
    if not pivots:
        return []

    ordered = sorted(
        pivots,
        key=lambda pivot: (pivot.price, pivot.timestamp_ms, pivot.candle_index),
    )

    valid_groups: list[tuple[FilteredPivot, ...]] = []
    for start in range(len(ordered)):
        for end in range(start, len(ordered)):
            group = tuple(ordered[start : end + 1])
            if _group_is_valid(group, tolerance_pct):
                valid_groups.append(group)

    unique_groups = _unique_groups(valid_groups)
    maximal_groups = _retain_maximal_groups(unique_groups)

    clusters: list[PivotCluster] = []
    for group in maximal_groups:
        center = mean(pivot.price for pivot in group)
        clusters.append(
            PivotCluster(
                center=center,
                score=len(group),
                pivots=tuple(group),
            )
        )

    clusters.sort(key=_cluster_sort_key)
    return clusters


def _group_is_valid(group: tuple[FilteredPivot, ...], tolerance_pct: float) -> bool:
    center = mean(pivot.price for pivot in group)
    if abs(center) <= 1e-12:
        return all(abs(pivot.price - center) <= 1e-12 for pivot in group)

    for pivot in group:
        deviation = abs(pivot.price - center) / abs(center)
        if deviation > tolerance_pct + 1e-12:
            return False
    return True


def _unique_groups(groups: list[tuple[FilteredPivot, ...]]) -> list[tuple[FilteredPivot, ...]]:
    unique: dict[tuple[tuple[str, int, int, float], ...], tuple[FilteredPivot, ...]] = {}
    for group in groups:
        key = tuple(_pivot_identity(pivot) for pivot in group)
        unique[key] = group
    return list(unique.values())


def _retain_maximal_groups(groups: list[tuple[FilteredPivot, ...]]) -> list[tuple[FilteredPivot, ...]]:
    group_sets = [set(_pivot_identity(pivot) for pivot in group) for group in groups]
    maximal: list[tuple[FilteredPivot, ...]] = []

    for idx, group in enumerate(groups):
        current = group_sets[idx]
        is_strict_subset = False
        for other_idx, other in enumerate(group_sets):
            if idx == other_idx:
                continue
            if current < other:
                is_strict_subset = True
                break
        if not is_strict_subset:
            maximal.append(group)

    return maximal


def _select_support_cluster(
    clusters: list[PivotCluster],
    price: float,
    min_confirmations: int = 2,
) -> PivotCluster | None:
    eligible = [cluster for cluster in clusters if cluster.center <= price]
    if not eligible:
        return None

    confirmed = [cluster for cluster in eligible if cluster.score >= min_confirmations]
    weak = [cluster for cluster in eligible if cluster.score < min_confirmations]
    pool = confirmed if confirmed else weak
    if not pool:
        return None

    return min(
        pool,
        key=lambda cluster: (
            price - cluster.center,
            -cluster.score,
            -cluster.center,
            _cluster_sort_key(cluster),
        ),
    )


def _select_resistance_cluster(
    clusters: list[PivotCluster],
    price: float,
    min_confirmations: int = 2,
) -> PivotCluster | None:
    eligible = [cluster for cluster in clusters if cluster.center >= price]
    if not eligible:
        return None

    confirmed = [cluster for cluster in eligible if cluster.score >= min_confirmations]
    weak = [cluster for cluster in eligible if cluster.score < min_confirmations]
    pool = confirmed if confirmed else weak
    if not pool:
        return None

    return min(
        pool,
        key=lambda cluster: (
            cluster.center - price,
            -cluster.score,
            cluster.center,
            _cluster_sort_key(cluster),
        ),
    )


def _cluster_sort_key(cluster: PivotCluster) -> tuple[float, int, tuple[tuple[str, int, int, float], ...]]:
    signature = tuple(_pivot_identity(pivot) for pivot in cluster.pivots)
    return (cluster.center, -cluster.score, signature)


def _pivot_identity(pivot: FilteredPivot) -> tuple[str, int, int, float]:
    return (pivot.kind, pivot.timestamp_ms, pivot.candle_index, round(pivot.price, 10))


def select_operational_level(
    *,
    side: Literal["SUPPORT", "RESISTANCE"],
    current_price: float,
    structural_cluster: PivotCluster | None,
    eligible_pivots: tuple[FilteredPivot, ...] | list[FilteredPivot],
    operational_range_pct: float | None = None,
    min_confirmations: int = 2,
) -> OperationalLevel:
    if not math.isfinite(current_price) or current_price <= 0:
        return OperationalLevel(
            price=None,
            source="none",
            confirmations=0,
            distance_pct=None,
            valid=False,
        )

    if operational_range_pct is not None and (not math.isfinite(operational_range_pct) or operational_range_pct <= 0):
        return OperationalLevel(
            price=None,
            source="none",
            confirmations=0,
            distance_pct=None,
            valid=False,
        )

    # 1. Primary: Structural Cluster check
    if structural_cluster is not None and math.isfinite(structural_cluster.center):
        level_price = structural_cluster.center
        correct_side = (level_price < current_price) if side == "SUPPORT" else (level_price > current_price)
        if correct_side and structural_cluster.score >= min_confirmations:
            dist_pct = abs(level_price - current_price) / current_price * 100.0
            if operational_range_pct is None or dist_pct <= operational_range_pct + 1e-12:
                return OperationalLevel(
                    price=level_price,
                    source="cluster",
                    confirmations=structural_cluster.score,
                    distance_pct=round(dist_pct, 4),
                    valid=True,
                )

    # 2. Fallback: Nearest valid individual pivot
    candidates: list[FilteredPivot] = []
    for pivot in eligible_pivots:
        if not math.isfinite(pivot.price):
            continue
        correct_side = (pivot.price < current_price) if side == "SUPPORT" else (pivot.price > current_price)
        if not correct_side:
            continue
        dist_pct = abs(pivot.price - current_price) / current_price * 100.0
        if operational_range_pct is None or dist_pct <= operational_range_pct + 1e-12:
            candidates.append(pivot)

    if candidates:
        best_pivot = min(
            candidates,
            key=lambda p: (
                abs(current_price - p.price),
                -p.timestamp_ms,
                -p.candle_index,
            ),
        )
        dist_pct = abs(best_pivot.price - current_price) / current_price * 100.0
        return OperationalLevel(
            price=best_pivot.price,
            source="pivot_fallback",
            confirmations=1,
            distance_pct=round(dist_pct, 4),
            valid=True,
        )

    # 3. None case
    return OperationalLevel(
        price=None,
        source="none",
        confirmations=0,
        distance_pct=None,
        valid=False,
    )


def derive_operational_range(
    *,
    current_price: float,
    swing_result: SwingRangeV2Result,
    operational_range_pct: float | None = None,
    min_operational_range_pct: float = 0.0,
    min_confirmations: int = 2,
) -> OperationalRangeResult:
    if operational_range_pct is None:
        sup_valid = swing_result.support < current_price
        res_valid = swing_result.resistance > current_price
        sup_dist = round(abs(current_price - swing_result.support) / current_price * 100.0, 4) if sup_valid else None
        res_dist = round(abs(swing_result.resistance - current_price) / current_price * 100.0, 4) if res_valid else None
        support_level = OperationalLevel(
            price=swing_result.support if sup_valid else None,
            source="cluster" if swing_result.selected_support_cluster is not None else "pivot_fallback",
            confirmations=swing_result.selected_support_cluster.score if swing_result.selected_support_cluster else 1,
            distance_pct=sup_dist,
            valid=sup_valid,
        )
        resistance_level = OperationalLevel(
            price=swing_result.resistance if res_valid else None,
            source="cluster" if swing_result.selected_resistance_cluster is not None else "pivot_fallback",
            confirmations=swing_result.selected_resistance_cluster.score if swing_result.selected_resistance_cluster else 1,
            distance_pct=res_dist,
            valid=res_valid,
        )
        has_levels = sup_valid and res_valid and swing_result.support < swing_result.resistance
        if has_levels:
            range_width = swing_result.resistance - swing_result.support
            range_mid = (swing_result.resistance + swing_result.support) / 2.0
            range_width_pct = (range_width / range_mid) * 100.0 if range_mid > 0 else 0.0
            too_narrow = (range_width_pct < min_operational_range_pct) if min_operational_range_pct > 0.0 else False
            is_valid = not too_narrow
        else:
            range_width = 0.0
            range_width_pct = 0.0
            too_narrow = False
            is_valid = False

        return OperationalRangeResult(
            support=support_level,
            resistance=resistance_level,
            operational_range_pct=0.0,
            is_valid=is_valid,
            range_width=range_width,
            range_width_pct=range_width_pct,
            too_narrow=too_narrow,
            min_operational_range_pct=min_operational_range_pct,
        )

    support_level = select_operational_level(
        side="SUPPORT",
        current_price=current_price,
        structural_cluster=swing_result.selected_support_cluster,
        eligible_pivots=swing_result.filtered_low_pivots,
        operational_range_pct=operational_range_pct,
        min_confirmations=min_confirmations,
    )

    resistance_level = select_operational_level(
        side="RESISTANCE",
        current_price=current_price,
        structural_cluster=swing_result.selected_resistance_cluster,
        eligible_pivots=swing_result.filtered_high_pivots,
        operational_range_pct=operational_range_pct,
        min_confirmations=min_confirmations,
    )

    has_levels = (
        support_level.valid
        and resistance_level.valid
        and support_level.price is not None
        and resistance_level.price is not None
        and support_level.price < resistance_level.price
    )

    if has_levels:
        range_width = resistance_level.price - support_level.price
        range_mid = (resistance_level.price + support_level.price) / 2.0
        range_width_pct = (range_width / range_mid) * 100.0 if range_mid > 0 else 0.0
        too_narrow = (range_width_pct < min_operational_range_pct) if min_operational_range_pct > 0.0 else False
        is_valid = not too_narrow
    else:
        range_width = 0.0
        range_width_pct = 0.0
        too_narrow = False
        is_valid = False

    return OperationalRangeResult(
        support=support_level,
        resistance=resistance_level,
        operational_range_pct=operational_range_pct,
        is_valid=is_valid,
        range_width=range_width,
        range_width_pct=range_width_pct,
        too_narrow=too_narrow,
        min_operational_range_pct=min_operational_range_pct,
    )
