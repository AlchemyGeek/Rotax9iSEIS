"""
climb.py — Climb-rate-correlated thermal analysis for the 916iS.

Existing oil/coolant tracking (fleet.py) only captures PEAK temperature
reached anywhere in a flight, with no regard for how it got there. This
module asks a different question: does cooling margin depend on HOW
STEEPLY you climbed, not just how long the flight was?

Two flights can reach the same peak oil temp via very different climb
profiles — a fast, steep climb stresses the cooling system differently
than a long, shallow one. Comparing rise rate without accounting for
climb rate (VS) conflates these. This module bins climb-phase data by
VS and computes temperature rise rate per bin, so a flight's thermal
behaviour is compared against other flights with a SIMILAR climb rate,
not the fleet average regardless of how the climb was flown.

Usage
-----
    from slingology_eis.climb import climb_thermal_profile, climb_trend

    profile = climb_thermal_profile(df)   # one flight
    trend_df = climb_trend(flights)        # across many flights, fleet.py style
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd


# VS bucket edges (fpm). A climb below 200 fpm barely counts as a climb
# for this purpose; bucket the rest into bands that separate "gentle",
# "normal", and "aggressive" climb behaviour.
VS_BUCKETS = [
    (200, 500,  "gentle"),
    (500, 1000, "normal"),
    (1000, 2000, "aggressive"),
]


def _vs_bucket(vs_fpm: float) -> Optional[str]:
    """Classify a VS value into a named bucket, or None if below the climb threshold."""
    for lo, hi, name in VS_BUCKETS:
        if lo <= vs_fpm < hi:
            return name
    if vs_fpm >= VS_BUCKETS[-1][1]:
        return VS_BUCKETS[-1][2]   # cap at the top bucket rather than dropping fast climbs
    return None


def climb_thermal_profile(df: pd.DataFrame, min_rows: int = 20) -> dict:
    """
    Compute climb-phase thermal rise rates for a single flight, binned by
    vertical speed.

    Requires 'phase' column (run detect_phases() first) and 'vs_fpm',
    'oil_temp_f', 'coolant_temp_f'.

    Returns
    -------
    dict with:
        available       : bool — whether enough climb data existed to compute this
        overall_climb_s : total seconds spent in CLIMB phase
        by_bucket       : dict keyed by VS bucket name, each containing:
            rows              : row count in this bucket
            mean_vs_fpm       : mean VS within the bucket
            oil_rise_f_per_min    : oil temp rise rate, °F/min, within the bucket
            coolant_rise_f_per_min: coolant temp rise rate, °F/min, within the bucket
        oil_rise_f_per_min_overall     : whole-climb oil rise rate, °F/min
        coolant_rise_f_per_min_overall : whole-climb coolant rise rate, °F/min
    """
    result = {"available": False, "overall_climb_s": 0, "by_bucket": {}}

    if "phase" not in df.columns:
        return result

    climb = df[df["phase"] == "CLIMB"].copy()
    if len(climb) < min_rows:
        return result

    result["overall_climb_s"] = len(climb)

    needed = ["vs_fpm", "oil_temp_f", "coolant_temp_f", "elapsed_s"]
    if not all(c in climb.columns for c in needed):
        return result

    climb = climb.dropna(subset=["vs_fpm"])
    if len(climb) < min_rows:
        return result

    # ── Overall climb-phase rise rate (whole climb, regardless of VS) ─────────
    result["oil_rise_f_per_min_overall"]     = _rise_rate(climb, "oil_temp_f")
    result["coolant_rise_f_per_min_overall"] = _rise_rate(climb, "coolant_temp_f")

    # ── Per-VS-bucket rise rate ────────────────────────────────────────────────
    climb["vs_bucket"] = climb["vs_fpm"].apply(_vs_bucket)
    for bucket_name in [b[2] for b in VS_BUCKETS]:
        sub = climb[climb["vs_bucket"] == bucket_name]
        if len(sub) < min_rows:
            continue
        result["by_bucket"][bucket_name] = {
            "rows": len(sub),
            "mean_vs_fpm": round(float(sub["vs_fpm"].mean()), 0),
            "oil_rise_f_per_min": _rise_rate(sub, "oil_temp_f"),
            "coolant_rise_f_per_min": _rise_rate(sub, "coolant_temp_f"),
        }

    result["available"] = bool(result["by_bucket"]) or (
        result["oil_rise_f_per_min_overall"] is not None
    )
    return result


def _rise_rate(seg: pd.DataFrame, temp_col: str) -> Optional[float]:
    """
    °F per minute rise rate for a temperature column across a segment,
    using a simple linear fit against elapsed time (robust to noise,
    unlike a raw first-vs-last difference).
    """
    sub = seg[["elapsed_s", temp_col]].dropna()
    if len(sub) < 5:
        return None
    t = sub["elapsed_s"].values.astype(float)
    y = sub[temp_col].values.astype(float)
    if np.std(t) == 0:
        return None
    slope_per_s, _ = np.polyfit(t, y, 1)   # °F per second
    return round(float(slope_per_s * 60), 2)   # °F per minute


def climb_report(df: pd.DataFrame) -> str:
    """Formatted text summary of climb thermal behaviour for one flight."""
    p = climb_thermal_profile(df)
    lines = ["── Climb Thermal Profile ───────────────────────────"]

    if not p["available"]:
        lines.append("  Insufficient climb data for this flight.")
        return "\n".join(lines)

    if p.get("oil_rise_f_per_min_overall") is not None:
        lines.append(f"  Overall climb ({p['overall_climb_s']}s): "
                     f"oil {p['oil_rise_f_per_min_overall']:+.1f}°F/min, "
                     f"coolant {p['coolant_rise_f_per_min_overall']:+.1f}°F/min")

    for bucket_name in [b[2] for b in VS_BUCKETS]:
        b = p["by_bucket"].get(bucket_name)
        if not b:
            continue
        lines.append(f"  {bucket_name.capitalize():<11} (~{b['mean_vs_fpm']:.0f} fpm, "
                     f"{b['rows']}s): oil {b['oil_rise_f_per_min']:+.1f}°F/min, "
                     f"coolant {b['coolant_rise_f_per_min']:+.1f}°F/min")

    return "\n".join(lines)


# ── Cross-flight aggregation ──────────────────────────────────────────────────

def climb_trend(
    flights: list[tuple[pd.DataFrame, object]],
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Build a per-flight climb-thermal metrics table across many flights,
    in the same spirit as fleet.build_flight_metrics().

    Each row: one flight's overall and per-bucket rise rates, plus
    engine_hours, so fleet.trend()/fleet.baseline() can be applied to
    the resulting columns directly (e.g. trend(result, "oil_rise_overall",
    x="engine_hours")).

    Note: this requires phases already detected on each DataFrame
    (i.e. flights should come from a pipeline that already ran
    detect_phases(), such as fleet.build_flight_metrics()'s internals —
    this function does NOT call detect_phases() itself).
    """
    rows = []
    for df, info in flights:
        fname = df["_source_file"].iloc[0] if "_source_file" in df.columns else "unknown"
        p = climb_thermal_profile(df)

        rec = {
            "source_file": fname,
            "date": df["datetime"].iloc[0].date() if "datetime" in df.columns else None,
            "engine_hours": getattr(info, "engine_hours", None),
            "climb_data_available": p["available"],
            "oil_rise_overall": p.get("oil_rise_f_per_min_overall"),
            "coolant_rise_overall": p.get("coolant_rise_f_per_min_overall"),
        }
        for bucket_name in [b[2] for b in VS_BUCKETS]:
            b = p["by_bucket"].get(bucket_name)
            rec[f"oil_rise_{bucket_name}"] = b["oil_rise_f_per_min"] if b else None
            rec[f"coolant_rise_{bucket_name}"] = b["coolant_rise_f_per_min"] if b else None
            rec[f"vs_mean_{bucket_name}"] = b["mean_vs_fpm"] if b else None

        rows.append(rec)
        if verbose:
            status = "✓" if p["available"] else "·"
            print(f"  {status} {fname}")

    return pd.DataFrame(rows)
