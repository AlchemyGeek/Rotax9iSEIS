"""
egt.py — EGT health analytics for the Rotax 916iS.

Key metrics:
  - EGT spread (Split) vs OM limits
  - Per-cylinder rank consistency
  - EGT4 elevation pattern
  - Trend across engine hours

All temperature limits from OM-916 i/C24, Chapter 2.1.

Usage
-----
    from slingology_eis.egt import egt_health, egt_trend

    report = egt_health(df)
    print(report)
"""

from __future__ import annotations
from typing import Optional
import numpy as np
import pandas as pd

EGT_COLS   = ["egt1_f", "egt2_f", "egt3_f", "egt4_f"]
EGT_MAX_F  = 1742.0   # 950°C — absolute per-cylinder max (OM 2.1)
SPREAD_HI_FLOW_F = 392.0  # 200°C — limit when fuel flow > 3 L/hr (OM 2.1)
SPREAD_LO_FLOW_F = 932.0  # 500°C — limit when fuel flow < 3 L/hr (OM 2.1)
LO_FLOW_GPH = 0.793    # 3 L/hr in gal/hr


def _cruise_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean mask for cruise-quality rows (engine running, stable)."""
    mask = pd.Series(True, index=df.index)
    if "phase" in df.columns:
        mask &= df["phase"] == "CRUISE"
    else:
        if "vs_fpm" in df.columns:
            mask &= df["vs_fpm"].abs() < 300
        if "ias_kt" in df.columns:
            mask &= df["ias_kt"] > 60
        if "rpm" in df.columns:
            mask &= df["rpm"] > 4000
    return mask


def egt_health(
    df: pd.DataFrame,
    min_rows: int = 30,
) -> dict:
    """
    Compute EGT health metrics for a single flight.

    Returns
    -------
    dict with keys:
        available_cylinders  : list of EGT column names present
        cruise_rows          : number of cruise-quality rows analysed
        per_cylinder         : dict of per-cyl stats (mean, max, rank_mean)
        spread_mean_f        : mean EGT spread during cruise
        spread_max_f         : max EGT spread during cruise
        spread_hi_limit_f    : applicable spread limit (392°F at normal flow)
        spread_pct_of_limit  : spread_mean as % of limit (>80% = approaching limit)
        egt4_elevation_f     : mean EGT4 − mean of EGT1–3 (expect positive for 916iS)
        rank_order           : most common cylinder rank order (hottest first)
        rank_stable          : True if the hottest cylinder is consistent
        limit_exceedances    : list of brief strings describing any limit hits
    """
    avail = [c for c in EGT_COLS if c in df.columns and not df[c].isna().all()]
    if not avail:
        return {"available_cylinders": [], "cruise_rows": 0}

    cruise = df[_cruise_mask(df)].copy()
    if len(cruise) < min_rows:
        cruise = df[df["rpm"].fillna(0) > 3000].copy()  # fallback

    result = {
        "available_cylinders": avail,
        "cruise_rows": len(cruise),
        "per_cylinder": {},
        "limit_exceedances": [],
    }

    if len(cruise) < 5:
        return result

    # ── Per-cylinder stats ────────────────────────────────────────────────────
    for col in avail:
        cyl = cruise[col].dropna()
        result["per_cylinder"][col] = {
            "mean_f": round(float(cyl.mean()), 1),
            "max_f":  round(float(cyl.max()), 1),
            "min_f":  round(float(cyl.min()), 1),
            "std_f":  round(float(cyl.std()), 1),
        }
        if cyl.max() > EGT_MAX_F:
            result["limit_exceedances"].append(
                f"{col} exceeded max {EGT_MAX_F}°F: peak={cyl.max():.0f}°F"
            )

    # ── EGT spread ────────────────────────────────────────────────────────────
    egt_data = cruise[avail].dropna(how="any")
    if len(egt_data) > 5:
        spread = egt_data.max(axis=1) - egt_data.min(axis=1)

        # Determine applicable limit (use fuel flow if available)
        if "fuel_flow_gph" in cruise.columns:
            hi_flow_mask = cruise["fuel_flow_gph"].reindex(egt_data.index) > LO_FLOW_GPH
            # Use limit for the majority mode
            limit_f = SPREAD_HI_FLOW_F if hi_flow_mask.mean() > 0.5 else SPREAD_LO_FLOW_F
        else:
            limit_f = SPREAD_HI_FLOW_F  # conservative default

        result["spread_mean_f"]      = round(float(spread.mean()), 1)
        result["spread_max_f"]       = round(float(spread.max()), 1)
        result["spread_hi_limit_f"]  = limit_f
        result["spread_pct_of_limit"] = round(float(spread.mean() / limit_f * 100), 1)

        if spread.max() > limit_f:
            result["limit_exceedances"].append(
                f"EGT spread exceeded limit {limit_f:.0f}°F: max={spread.max():.0f}°F"
            )

    # ── EGT4 elevation (expected pattern for 916iS) ───────────────────────────
    if "egt4_f" in avail and len(avail) > 1:
        others  = [c for c in avail if c != "egt4_f"]
        mean4   = cruise["egt4_f"].mean()
        mean_rest = cruise[others].stack().mean()
        result["egt4_elevation_f"] = round(float(mean4 - mean_rest), 1)

    # ── Cylinder rank order (most common hottest→coldest ordering) ────────────
    if len(avail) >= 2:
        ranks  = egt_data[avail].rank(axis=1, ascending=False)
        # Most common rank for each cylinder
        hottest_col = egt_data[avail].idxmax(axis=1).mode()
        result["rank_order"] = (
            egt_data[avail].mean()
            .sort_values(ascending=False)
            .index.tolist()
        )
        result["rank_stable"] = len(hottest_col) == 1  # True if one cylinder dominates

    return result


def egt_trend(
    flights: list[tuple[pd.DataFrame, object]],
) -> pd.DataFrame:
    """
    Compute EGT health metrics across multiple flights and return a
    trend DataFrame indexed by engine hours (or flight date).

    Parameters
    ----------
    flights : list of (DataFrame, AirframeInfo) tuples from loader.load_directory()

    Returns
    -------
    pd.DataFrame with one row per flight, columns for key EGT metrics.
    """
    records = []
    for df, info in flights:
        h = egt_health(df)
        rec = {
            "date":            df["datetime"].iloc[0].date() if "datetime" in df.columns else None,
            "engine_hours":    info.engine_hours if hasattr(info, "engine_hours") else None,
            "cruise_rows":     h.get("cruise_rows", 0),
            "spread_mean_f":   h.get("spread_mean_f"),
            "spread_max_f":    h.get("spread_max_f"),
            "spread_pct_limit":h.get("spread_pct_of_limit"),
            "egt4_elevation_f":h.get("egt4_elevation_f"),
            "rank_stable":     h.get("rank_stable"),
            "exceedances":     len(h.get("limit_exceedances", [])),
        }
        for col in EGT_COLS:
            if col in h.get("per_cylinder", {}):
                rec[f"{col}_mean"] = h["per_cylinder"][col]["mean_f"]
                rec[f"{col}_max"]  = h["per_cylinder"][col]["max_f"]
        records.append(rec)

    return pd.DataFrame(records)


def egt_report(df: pd.DataFrame) -> str:
    """Return a formatted EGT health summary for one flight."""
    h = egt_health(df)
    lines = ["── EGT Health ─────────────────────────────────────"]

    if not h.get("available_cylinders"):
        lines.append("  No EGT data available.")
        return "\n".join(lines)

    lines.append(f"  Cylinders: {', '.join(h['available_cylinders'])}")
    lines.append(f"  Cruise rows analysed: {h['cruise_rows']}")

    if "per_cylinder" in h:
        lines.append("  Per-cylinder (cruise mean / max):")
        for col, stats in h["per_cylinder"].items():
            cyl = col.replace("egt", "").replace("_f", "")
            lines.append(f"    Cyl {cyl}: mean {stats['mean_f']:.0f}°F  max {stats['max_f']:.0f}°F")

    if "spread_mean_f" in h:
        pct = h.get("spread_pct_of_limit", 0)
        flag = "⚠" if pct > 80 else "✓"
        lines.append(f"  EGT spread: mean {h['spread_mean_f']:.0f}°F  "
                     f"max {h['spread_max_f']:.0f}°F  "
                     f"limit {h['spread_hi_limit_f']:.0f}°F  "
                     f"({pct:.0f}% of limit) {flag}")

    if "egt4_elevation_f" in h:
        elev = h["egt4_elevation_f"]
        note = "(typical for 916iS — turbo exhaust proximity)" if elev > 0 else ""
        lines.append(f"  EGT4 elevation vs EGT1–3: {elev:+.0f}°F {note}")

    if "rank_order" in h:
        order = " > ".join(c.replace("egt","").replace("_f","") for c in h["rank_order"])
        stable = "stable" if h.get("rank_stable") else "variable"
        lines.append(f"  Cylinder heat rank (hottest→coldest): {order} ({stable})")

    if h.get("limit_exceedances"):
        lines.append("  ⚠ Limit exceedances:")
        for exc in h["limit_exceedances"]:
            lines.append(f"    {exc}")

    return "\n".join(lines)
