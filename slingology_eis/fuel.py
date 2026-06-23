"""
fuel.py — Fuel analytics for the 916iS.

Key fact: Rotax FADEC fuel flow is a MODEL-BASED CALCULATION, not a
physical sensor measurement — there is no flow sensor in the fuel
line. The OM states a ±10% tolerance at cruise conditions.

Note on calibration: an earlier version of this module computed a
K_fuel correction factor from logged pump receipts (fadec_gallons vs.
pump_gallons across flights). That machinery was removed — for
full-to-full refuelling (the normal case for this aircraft, which
carries fuel for many hours and multiple flights per tank), gallons
added at the pump already equals true consumption directly. No
flight-log-based calibration adds value over that direct measurement.
See CHANGELOG.md (0.6.0) and the research paper for the full reasoning.

Standard float-type fuel quantity senders are unreliable for
consumption calculations (attitude-sensitive). This module uses
FADEC fuel flow integration as the primary signal and tank
readings only for gross sanity checks (tank_sanity_check).

Usage
-----
    from slingology_eis.fuel import (
        integrate_fuel, cruise_efficiency, tank_sanity_check, fuel_report
    )
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ── Integration ───────────────────────────────────────────────────────────────

def integrate_fuel(
    df: pd.DataFrame,
    k_fuel: Optional[float] = None,
    phase_filter: Optional[list[str]] = None,
) -> dict:
    """
    Integrate FADEC fuel flow over a flight to get total consumption.

    Parameters
    ----------
    df : pd.DataFrame
        Loaded flight log with 'fuel_flow_gph' and 'elapsed_s' columns.
    k_fuel : float, optional
        Calibration factor. If None, raw FADEC value used.
    phase_filter : list[str], optional
        If provided (e.g., ["CRUISE"]), only integrate fuel for those phases.

    Returns
    -------
    dict with:
        fadec_gallons     : FADEC raw integrated consumption
        corrected_gallons : K_fuel corrected consumption (same as fadec if k_fuel=None)
        k_fuel_applied    : calibration factor used
        duration_s        : seconds covered
    """
    work = df.copy()

    if phase_filter and "phase" in work.columns:
        work = work[work["phase"].isin(phase_filter)]

    if "fuel_flow_gph" not in work.columns or work["fuel_flow_gph"].isna().all():
        return {"fadec_gallons": None, "corrected_gallons": None,
                "k_fuel_applied": k_fuel, "duration_s": 0}

    # Trapezoidal integration: flow [gal/hr] × dt [s] / 3600 [s/hr]
    flow = work["fuel_flow_gph"].fillna(0)
    dt   = work["elapsed_s"].diff().fillna(1)   # 1-second intervals nominally
    raw_gallons = (flow * dt / 3600).sum()

    corrected = raw_gallons * k_fuel if k_fuel is not None else raw_gallons

    return {
        "fadec_gallons":     round(float(raw_gallons), 3),
        "corrected_gallons": round(float(corrected), 3),
        "k_fuel_applied":    k_fuel,
        "duration_s":        float(dt.sum()),
    }


# ── Efficiency metrics ────────────────────────────────────────────────────────

def cruise_efficiency(
    df: pd.DataFrame,
    k_fuel: Optional[float] = None,
    min_duration_s: float = 120,
) -> Optional[dict]:
    """
    Compute ECO-cruise efficiency metrics.

    Filters to stable cruise segments only:
    - Phase == CRUISE (if phases detected) OR
    - VS < 200 fpm, IAS > 60 kt, RPM stable

    Returns nmpg (nautical miles per gallon) and related stats.
    """
    if "phase" in df.columns:
        cruise = df[df["phase"] == "CRUISE"].copy()
    else:
        cruise = df[
            (df["vs_fpm"].abs() < 200) &
            (df["ias_kt"] > 60) &
            (df["rpm"] > 4000)
        ].copy() if all(c in df.columns for c in ["vs_fpm", "ias_kt", "rpm"]) else pd.DataFrame()

    if len(cruise) < min_duration_s:
        return None

    fuel_data = integrate_fuel(cruise, k_fuel=k_fuel)
    gallons   = fuel_data["corrected_gallons"] or fuel_data["fadec_gallons"]

    if not gallons or gallons <= 0:
        return None

    # Distance covered during cruise: integrate ground speed
    nm = 0.0
    if "gnd_spd_kt" in cruise.columns:
        gs  = cruise["gnd_spd_kt"].fillna(0)
        dt  = cruise["elapsed_s"].diff().fillna(1)
        nm  = (gs * dt / 3600).sum()    # kt × hr = nm

    nmpg        = nm / gallons if gallons > 0 else None
    mean_ff_gph = cruise["fuel_flow_gph"].mean() if "fuel_flow_gph" in cruise.columns else None
    mean_ias    = cruise["ias_kt"].mean() if "ias_kt" in cruise.columns else None
    mean_rpm    = cruise["rpm"].mean() if "rpm" in cruise.columns else None
    mean_da     = cruise["da_ft"].mean() if "da_ft" in cruise.columns else None

    return {
        "cruise_duration_s":      len(cruise),
        "cruise_nm":              round(nm, 1),
        "cruise_gallons":         round(gallons, 2),
        "nmpg":                   round(nmpg, 2) if nmpg else None,
        "mean_fuel_flow_gph":     round(mean_ff_gph, 2) if mean_ff_gph else None,
        "mean_ias_kt":            round(mean_ias, 1) if mean_ias else None,
        "mean_rpm":               round(mean_rpm, 0) if mean_rpm else None,
        "mean_density_alt_ft":    round(mean_da, 0) if mean_da else None,
        "k_fuel_applied":         k_fuel,
    }


# ── Fuel sender sanity check ──────────────────────────────────────────────────

def tank_sanity_check(
    df: pd.DataFrame,
    k_fuel: Optional[float] = None,
    tolerance_gal: float = 2.0,
) -> dict:
    """
    Compare FADEC-integrated consumption against tank quantity delta.

    Tank senders are unreliable (attitude-sensitive) so this is a
    gross sanity check only. A discrepancy > tolerance_gal is flagged
    as a data quality note, not a hard error.
    """
    result = {"status": "ok", "notes": []}

    fuel_result = integrate_fuel(df, k_fuel=k_fuel)
    fadec_used  = fuel_result["corrected_gallons"]

    # Tank delta: use R tank by default (L tank notorious for phantom readings)
    for tank, col in [("R", "fuel_qty_r_gal"), ("L", "fuel_qty_l_gal")]:
        if col not in df.columns:
            continue
        qty = df[col].dropna()
        if len(qty) < 2:
            continue
        # Use 10th and 90th percentile to reduce sender noise at extremes
        start = qty.quantile(0.90)
        end   = qty.quantile(0.10)
        delta = start - end    # positive = consumed
        if delta < 0 or delta > 30:  # implausible
            result["notes"].append(
                f"Tank {tank} sender data implausible (start≈{start:.1f}, end≈{end:.1f} gal)"
            )
            continue
        if fadec_used is not None:
            diff = abs(fadec_used - delta)
            if diff > tolerance_gal:
                result["status"] = "flag"
                result["notes"].append(
                    f"Tank {tank} delta ({delta:.1f} gal) vs FADEC ({fadec_used:.1f} gal) "
                    f"discrepancy {diff:.1f} gal — tank senders are attitude-sensitive "
                    f"and may simply be reading inaccurately"
                )

    return result


# ── Text report ───────────────────────────────────────────────────────────────

def fuel_report(df: pd.DataFrame, k_fuel: Optional[float] = None) -> str:
    """Return a formatted fuel analysis summary for one flight."""
    lines = ["── Fuel Analysis ─────────────────────────────────"]

    total = integrate_fuel(df, k_fuel=k_fuel)
    lines.append(f"  Total FADEC (raw):      {total['fadec_gallons']:.2f} gal")
    if k_fuel:
        lines.append(f"  K_fuel applied:         {k_fuel:.3f}")
        lines.append(f"  Total corrected:        {total['corrected_gallons']:.2f} gal")

    eff = cruise_efficiency(df, k_fuel=k_fuel)
    if eff:
        lines.append(f"  Cruise nmpg:            {eff['nmpg']} nm/gal")
        lines.append(f"  Cruise fuel flow (mean):{eff['mean_fuel_flow_gph']} gal/hr")
        lines.append(f"  Cruise distance:        {eff['cruise_nm']} nm")

    sanity = tank_sanity_check(df, k_fuel=k_fuel)
    if sanity["notes"]:
        for note in sanity["notes"]:
            lines.append(f"  ⚠  {note}")

    return "\n".join(lines)
