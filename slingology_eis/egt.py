"""
egt.py — EGT health analytics for the Rotax 916iS.

Key metrics:
  - EGT spread (Split) vs OM limits
  - Per-cylinder balance (each cylinder vs. the mean of the others)
  - Hottest cylinder, its margin over the next, and rank consistency
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

# Spec 08 §9. Below this hottest-vs-next gap the "hottest cylinder" is
# treated as ambiguous — two cylinders within a few °F trade places on
# noise alone.
MARGIN_MIN_F = 15.0
# Spec 08 §4: rank_stable means the modal hottest cylinder was hottest in
# at least this share of cruise samples.
RANK_STABLE_SHARE = 0.8


def cyl_number(col: str) -> int:
    """'egt3_f' -> 3."""
    return int(col.replace("egt", "").replace("_f", ""))


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
        egt{n}_deviation_f   : mean EGTn − mean of the other cylinders, per cylinder
        egt4_elevation_f     : deprecated alias of egt4_deviation_f (Spec 08 §4)
        hottest_cyl          : cylinder number with the highest cruise-mean EGT
        hottest_margin_f     : cruise-mean EGT of hottest − second hottest
        rank_order           : EGT column names by cruise mean, hottest first
        rank_stable          : True if the modal hottest cylinder was hottest in
                               ≥ RANK_STABLE_SHARE of cruise samples
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

    # ── Per-cylinder balance (Spec 08 §4) ─────────────────────────────────────
    # Each cylinder's cruise mean vs. the pooled mean of the others — no
    # cylinder is assumed to be the hot one. Pooled over all cruise rows
    # (not the row-aligned egt_data) so egt4_deviation_f stays identical to
    # the egt4_elevation_f it replaces.
    if len(avail) > 1:
        for col in avail:
            others = [c for c in avail if c != col]
            dev = cruise[col].mean() - cruise[others].stack().mean()
            if not pd.isna(dev):
                result[f"egt{cyl_number(col)}_deviation_f"] = round(float(dev), 1)
        if "egt4_deviation_f" in result:
            result["egt4_elevation_f"] = result["egt4_deviation_f"]

    # ── Hottest cylinder and rank order ───────────────────────────────────────
    if len(avail) >= 2 and len(egt_data) > 0:
        means = egt_data[avail].mean().sort_values(ascending=False)
        result["rank_order"] = means.index.tolist()
        result["hottest_cyl"] = cyl_number(means.index[0])
        result["hottest_margin_f"] = round(float(means.iloc[0] - means.iloc[1]), 1)
        per_sample_hottest = egt_data[avail].idxmax(axis=1)
        modal_share = per_sample_hottest.value_counts(normalize=True).iloc[0]
        result["rank_stable"] = bool(modal_share >= RANK_STABLE_SHARE)

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
            "hottest_cyl":     h.get("hottest_cyl"),
            "hottest_margin_f":h.get("hottest_margin_f"),
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

    devs = [(n, h[f"egt{n}_deviation_f"]) for n in range(1, 5) if f"egt{n}_deviation_f" in h]
    if devs:
        lines.append("  Cylinder balance vs. mean of the others: "
                     + "  ".join(f"Cyl {n} {d:+.0f}°F" for n, d in devs))

    if "hottest_cyl" in h:
        ambiguous = f" — ambiguous, below the {MARGIN_MIN_F:.0f}°F margin" if h["hottest_margin_f"] < MARGIN_MIN_F else ""
        lines.append(f"  Hottest: Cyl {h['hottest_cyl']} "
                     f"(+{h['hottest_margin_f']:.0f}°F over next{ambiguous})")

    if "rank_order" in h:
        order = " > ".join(str(cyl_number(c)) for c in h["rank_order"])
        stable = "stable" if h.get("rank_stable") else "variable"
        lines.append(f"  Cylinder heat rank (hottest→coldest): {order} ({stable})")

    if h.get("limit_exceedances"):
        lines.append("  ⚠ Limit exceedances:")
        for exc in h["limit_exceedances"]:
            lines.append(f"    {exc}")

    return "\n".join(lines)
