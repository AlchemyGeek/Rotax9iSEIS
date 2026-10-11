"""
trends.py — Spec 12's change statistic: recent window, shift (with R8
stratification/fallback, shared with Spec 09's filter monitor via
filters.points_baseline/comparison_set), bend, and level crossing.

Pure functions operating on the `points` shape `update_fleet` already
builds for every fleet metric ({flight_id, date, x, value, band?}) — no
FleetAnalysis object needed, since this runs *inside* update_fleet
before one exists.
"""
from __future__ import annotations

from typing import Optional

from .filters import comparison_set, points_baseline


def recent_window(
    points: list[dict], hours_min: float, min_flights: int, max_flights: int,
) -> Optional[dict]:
    """
    Spec 12 §5.1. Walking back from the newest eligible flight (by engine
    hours, date tie-break), the window is the smallest set of flights
    such that both hold: hours spanned >= hours_min, count >= min_flights
    — capped at max_flights. Returns None (RECENT_WINDOW_LOW_N) when
    fewer than min_flights eligible flights exist at all.

    "Eligible" here means a non-null value and a non-null x (engine
    hours) — the window is sized in hours, so a point with no hours
    metadata can't anchor it.
    """
    from .operations import _chronological

    seq = _chronological([p for p in points if p.get("value") is not None and p.get("x") is not None])
    n = len(seq)
    if n < min_flights:
        return None

    limit = min(n, max_flights)
    count = min_flights
    hours_spanned = seq[-count:][-1]["x"] - seq[-count:][0]["x"]
    while count < limit and hours_spanned < hours_min:
        count += 1
        window = seq[-count:]
        hours_spanned = window[-1]["x"] - window[0]["x"]

    window = seq[-count:]
    hours_spanned = window[-1]["x"] - window[0]["x"]
    capped = count >= max_flights and hours_spanned < hours_min and max_flights <= n

    return {
        "flight_ids": [p["flight_id"] for p in window],
        "n": len(window),
        "hours_from": window[0]["x"],
        "hours_to": window[-1]["x"],
        "mean": sum(p["value"] for p in window) / len(window),
        "capped": capped,
    }


def _ols_slope_se(xs: list[float], ys: list[float]) -> Optional[tuple[float, float]]:
    """(slope, standard error of slope) by ordinary least squares.
    None if x has no variance or n < 3."""
    n = len(xs)
    if n < 3:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    if n <= 2:
        return slope, 0.0
    mse = sum(r ** 2 for r in residuals) / (n - 2)
    se = (mse / sxx) ** 0.5
    return slope, se


def bend(
    window_points: list[dict], reference_points: list[dict], worsening: str, n_min: int,
) -> Optional[dict]:
    """
    Spec 12 §5.4. Fits a slope (value vs. engine hours) over each of the
    reference and the recent window; fires when the recent slope differs
    from the reference slope by more than 2x the reference slope's SE,
    in the worsening direction. None (not computed) below n_min on
    either side.
    """
    ref_xy = [(p["x"], p["value"]) for p in reference_points if p.get("x") is not None and p.get("value") is not None]
    rec_xy = [(p["x"], p["value"]) for p in window_points if p.get("x") is not None and p.get("value") is not None]
    if len(ref_xy) < n_min or len(rec_xy) < n_min:
        return None
    ref_fit = _ols_slope_se([x for x, _ in ref_xy], [y for _, y in ref_xy])
    rec_fit = _ols_slope_se([x for x, _ in rec_xy], [y for _, y in rec_xy])
    if ref_fit is None or rec_fit is None:
        return None
    ref_slope, ref_se = ref_fit
    rec_slope, _ = rec_fit
    delta = rec_slope - ref_slope
    threshold = 2 * ref_se
    if worsening == "higher":
        fires = delta > threshold
    elif worsening == "lower":
        fires = delta < -threshold
    else:
        fires = abs(delta) > threshold
    return {"reference_slope": ref_slope, "recent_slope": rec_slope, "fires": fires}


def level_crossing(
    recent_mean: Optional[float],
    reference_mean_unstratified: Optional[float],
    worsening: str,
    om_limit: Optional[dict],
    filter_edge: Optional[float],
    om_margin_fraction: float,
) -> dict:
    """
    Spec 12 §5.5. `om_limit` is {"limit_value": float} from
    `limits.limit_catalog()` for the metric's OM limit, or None if it has
    none. `filter_edge` is the already-resolved effective engine-unit
    threshold of an active Spec 09 filter on the metric's limit, or None.
    Both checks use the recent window's *unstratified* mean, since limits
    aren't weather-dependent.
    """
    out = {"om_margin": False, "filter_edge": False}
    if recent_mean is None:
        return out
    if om_limit is not None and reference_mean_unstratified is not None and worsening in ("higher", "lower"):
        limit_value = om_limit["limit_value"]
        headroom = abs(limit_value - reference_mean_unstratified)
        margin_line = (
            limit_value - om_margin_fraction * headroom if worsening == "higher"
            else limit_value + om_margin_fraction * headroom
        )
        out["limit"] = limit_value
        out["margin_line"] = margin_line
        out["om_margin"] = recent_mean >= margin_line if worsening == "higher" else recent_mean <= margin_line
    if filter_edge is not None:
        out["filter_edge_value"] = filter_edge
        out["filter_edge"] = recent_mean >= filter_edge
    return out


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> Optional[float]:
    """
    Pooled two-proportion z for (x1/n1) vs (x2/n2). None when either
    group is empty, or when the pooled proportion is exactly 0 or 1 —
    the only way that happens is both groups' shares already being
    equal at that boundary (both all-zero or both all-one), where the
    difference is 0 and frequency never qualifies anyway. A zero
    *reference* share alone (the interesting qualifying case) still
    pools to a value strictly between 0 and 1 whenever the recent share
    is nonzero, so z is well-defined there.
    """
    if n1 == 0 or n2 == 0:
        return None
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    denom = (p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) ** 0.5
    if denom == 0:
        return None
    return (p1 - p2) / denom


def event_frequency(
    points: list[dict],
    window: dict,
    reference_ids: list[str],
    has_event,
    frequency_delta: float,
    n_min: int,
) -> dict:
    """
    Spec 12 §5.8. Share of eligible flights with >=1 event, in the
    recent window and in the reference — `window`/`reference_ids` come
    from the limit's own full-coverage metric (`time_above_pct`, or
    `block_s` for overboost, both populated on every checked flight,
    unlike the sparse `peak_excess`), so frequency and the event strip
    always agree on which flights are "eligible". `has_event` is a
    value -> bool predicate: `value > 0` for an ordinary limit's
    `time_above_pct`; `value > limit_value` for overboost's `block_s`,
    whose value is a continuous block length present on nearly every
    flight, not a sparse exceedance flag.

    Qualifies when the reference has at least n_min flights and the
    recent share exceeds the reference share by at least
    frequency_delta — except when the reference share is 0 and the
    recent window has exactly one event, too thin a signal to call a
    change even though the delta crosses the threshold.
    """
    window_ids = set(window["flight_ids"])
    reference_id_set = set(reference_ids)
    recent_pts = [p for p in points if p["flight_id"] in window_ids]
    ref_pts = [p for p in points if p["flight_id"] in reference_id_set]
    n_rec, n_ref = len(recent_pts), len(ref_pts)
    events_rec = sum(1 for p in recent_pts if has_event(p.get("value")))
    events_ref = sum(1 for p in ref_pts if has_event(p.get("value")))
    share_rec = events_rec / n_rec if n_rec else None
    share_ref = events_ref / n_ref if n_ref else None
    delta = (share_rec - share_ref) if (share_rec is not None and share_ref is not None) else None
    z = two_proportion_z(events_rec, n_rec, events_ref, n_ref)

    qualifies = False
    if delta is not None and n_ref >= n_min and delta >= frequency_delta:
        qualifies = not (share_ref == 0 and events_rec == 1)

    return {
        "recent": {"events": events_rec, "flights": n_rec},
        "reference": {"events": events_ref, "flights": n_ref},
        "delta": round(delta, 4) if delta is not None else None,
        "z": round(z, 4) if z is not None else None,
        "qualifies": qualifies,
    }


def shift_stat(
    points: list[dict],
    window: dict,
    reference_ids: list[str],
    band_kind: Optional[str],
    n_min: int,
    std_floor: float = 0.0,
) -> dict:
    """
    Spec 12 §5.2-§5.3. `reference_ids` is the reference membership —
    every eligible point not in the window for a rolling reference, or
    the user's pinned set (Phase 2). Uses filters.points_baseline/
    comparison_set directly, the same functions Spec 09's filter monitor
    uses, so the two can never disagree about the same flights
    (acceptance 2).
    """
    window_ids = set(window["flight_ids"])
    window_points = [p for p in points if p["flight_id"] in window_ids and p.get("value") is not None]
    n_rec = len(window_points)
    recent_mean = sum(p["value"] for p in window_points) / n_rec if n_rec else None

    frozen = points_baseline(points, reference_ids)

    def _floor(std):
        return max(std, std_floor) if std is not None else None

    by_band: dict[str, int] = {}
    unmatched = 0
    z_values = []
    scopes_used: set[str] = set()
    for p in window_points:
        band = p.get("band") if band_kind else None
        stats, comp = comparison_set(frozen, band, n_min=n_min)
        std = _floor(stats.get("std"))
        if stats.get("mean") is None or not std:
            unmatched += 1
            continue
        z_values.append((p["value"] - stats["mean"]) / std)
        scopes_used.add(comp["scope"])
        if comp["scope"] == "band":
            by_band[comp["band"]] = by_band.get(comp["band"], 0) + 1

    insufficient = n_rec == 0 or unmatched > n_rec / 2
    comparison = {
        "scope": "insufficient" if insufficient else (
            "all" if band_kind is None else
            ("band" if scopes_used == {"band"} else ("all" if scopes_used == {"all"} else "mixed"))
        ),
        "by_band": by_band,
        "unmatched": unmatched,
    }

    shift_z = None
    if not insufficient:
        if band_kind is None:
            std = _floor(frozen.get("std"))
            if recent_mean is not None and frozen.get("mean") is not None and std:
                shift_z = (recent_mean - frozen["mean"]) / (std / (n_rec ** 0.5))
        elif z_values:
            # Spec 12 §5.2: the multiplier is n_rec (the window size), not
            # the matched-only count — matched flights' z-scores average
            # out the unmatched ones' absence, but the window's own size
            # still sets the statistic's power.
            shift_z = (sum(z_values) / len(z_values)) * (n_rec ** 0.5)

    direction = "none"
    if shift_z is not None and shift_z != 0:
        direction = "higher" if shift_z > 0 else "lower"

    return {
        "recent": {
            "flight_ids": window["flight_ids"], "n": n_rec,
            "hours_from": window["hours_from"], "hours_to": window["hours_to"], "mean": recent_mean,
        },
        "reference": frozen,
        "shift_z": round(shift_z, 4) if shift_z is not None else None,
        "direction": direction,
        "comparison": comparison,
    }
