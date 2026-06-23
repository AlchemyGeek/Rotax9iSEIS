"""
phases.py — Automatic flight phase detection for 916iS G3X logs.

No manual labelling required. Uses a state machine with hysteresis
to segment each flight into named phases.

Phases
------
  PRE_START      Engine not yet running, avionics on
  ENGINE_START   RPM transitioning from 0 to idle
  WARMUP         Idle RPM, oil/coolant temps rising, aircraft stationary
  TAXI           Low RPM, low speed, stable altitude
  TAKEOFF_ROLL   High RPM, accelerating, on ground
  CLIMB          Climbing, RPM high, power high
  CRUISE         Level flight, stable speed
  DESCENT        Descending, power reducing
  APPROACH       Low altitude, variable VS, speed reducing
  LANDING_ROLL   Speed decelerating through Vr toward zero
  SHUTDOWN       RPM zero, flight complete
  UNKNOWN        Transition / ambiguous

Usage
-----
    from slingology_eis.phases import detect_phases

    df = detect_phases(df, field_elev_ft=347)   # KPAE field elevation
    print(df["phase"].value_counts())
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
import numpy as np
import pandas as pd


class Phase(str, Enum):
    PRE_START    = "PRE_START"
    ENGINE_START = "ENGINE_START"
    WARMUP       = "WARMUP"
    TAXI         = "TAXI"
    TAKEOFF_ROLL = "TAKEOFF_ROLL"
    CLIMB        = "CLIMB"
    CRUISE       = "CRUISE"
    DESCENT      = "DESCENT"
    APPROACH     = "APPROACH"
    LANDING_ROLL = "LANDING_ROLL"
    SHUTDOWN     = "SHUTDOWN"
    UNKNOWN      = "UNKNOWN"


# ── Smoothing helper ──────────────────────────────────────────────────────────

def _smooth(series: pd.Series, window: int = 5) -> pd.Series:
    """Median-smooth a series to reduce noise at phase boundaries."""
    return series.rolling(window, center=True, min_periods=1).median()


def _estimate_field_elevation(df: pd.DataFrame) -> float:
    """
    Estimate departure field elevation (ft MSL) directly from the log,
    using the barometric altitude while the engine is at idle/ground RPM
    and the aircraft is stationary, before the first takeoff roll.

    This makes phase detection self-calibrating per flight rather than
    relying on a single hardcoded home-field elevation — important for
    cross-country flights that depart from or land at fields with very
    different elevations (e.g. a Pacific Northwest home field vs. a
    high-elevation destination airport).

    Note: this reflects INDICATED altitude under whatever altimeter
    setting (baro_inhg) was dialed in at the time, not the airport's
    true surveyed elevation — those can differ by 100+ ft depending on
    local pressure. That's fine for our purposes here: AGL is computed
    as a delta from this same baseline, so the offset cancels out even
    though the absolute number won't match charted field elevation.
    """
    if "baro_alt_ft" not in df.columns or "rpm" not in df.columns:
        return 0.0

    ias = df["ias_kt"] if "ias_kt" in df.columns else pd.Series(0, index=df.index)

    # Widen progressively if the strict ground filter doesn't yield enough
    # valid (non-NaN) altitude samples — e.g. a brief sensor dropout right
    # at engine start can leave the first few "ground" rows all NaN.
    for rpm_ceiling, ias_ceiling, min_valid in [
        (2500, 5,  10),    # strict: clearly stationary, engine idling
        (3000, 15, 10),    # looser: still clearly on the ground
        (4500, 30, 5),     # taxi-speed fallback
    ]:
        candidate = df[
            (df["rpm"].fillna(9999) < rpm_ceiling) &
            (ias.fillna(99) < ias_ceiling)
        ]["baro_alt_ft"].dropna()
        if len(candidate) >= min_valid:
            return float(candidate.iloc[:60].median())

    # Last resort: first non-NaN altitude anywhere in the log
    first_valid = df["baro_alt_ft"].dropna()
    return float(first_valid.iloc[0]) if len(first_valid) else 0.0


# ── Main detector ─────────────────────────────────────────────────────────────

def detect_phases(
    df: pd.DataFrame,
    field_elev_ft: Optional[float] = None,
    warmup_oil_target_f: float = 122.0,   # 50°C — OM takeoff minimum
    min_cruise_vs_fpm: float = 200,        # VS must be below this for cruise (entry)
    cruise_exit_vs_fpm: Optional[float] = None,  # VS to LEAVE cruise (exit, wider band)
    min_cruise_duration_s: float = 60,     # Must hold cruise for 60s
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Add a 'phase' column to df with automatic phase labels.

    Parameters
    ----------
    df : pd.DataFrame
        Loaded and normalised log (from loader.load_log).
    field_elev_ft : float, optional
        Departure field elevation in feet MSL, for AGL approximation.
        If None (default), this is AUTO-ESTIMATED from the log itself —
        the median barometric altitude while on the ground before the
        first takeoff. Pass an explicit value only if you need to override
        this (e.g. a log that starts mid-flight with no ground segment).
    warmup_oil_target_f : float
        Oil temp target marking end of warmup (default 50°C / 122°F, OM min).
    min_cruise_vs_fpm : float
        Max absolute vertical speed to ENTER cruise from climb/descent (fpm).
    cruise_exit_vs_fpm : float, optional
        Vertical speed threshold to LEAVE cruise for climb/descent (fpm).
        Default: 1.5x min_cruise_vs_fpm. Deliberately wider than the entry
        threshold (hysteresis) so ordinary VS noise while nominally level
        doesn't cause rapid CRUISE/CLIMB/DESCENT flicker.
    min_cruise_duration_s : float
        Minimum seconds of stable VS to enter CRUISE phase.
    verbose : bool
        Print phase transition log.

    Returns
    -------
    df : pd.DataFrame
        Same DataFrame with 'phase' (str) and 'phase_changed' (bool) columns added.
    """
    df = df.copy()
    n = len(df)

    if cruise_exit_vs_fpm is None:
        cruise_exit_vs_fpm = min_cruise_vs_fpm * 1.5

    if field_elev_ft is None:
        field_elev_ft = _estimate_field_elevation(df)
        if field_elev_ft is None or (isinstance(field_elev_ft, float) and pd.isna(field_elev_ft)):
            field_elev_ft = 0.0
        if verbose:
            print(f"  (auto-estimated field elevation: {field_elev_ft:.0f} ft MSL)")

    # ── Smoothed working signals ──────────────────────────────────────────────
    rpm    = _smooth(df["rpm"].fillna(0),         window=5)
    ias    = _smooth(df["ias_kt"].fillna(0),      window=5) if "ias_kt" in df.columns else pd.Series(np.zeros(n))
    vs     = _smooth(df["vs_fpm"].fillna(0),      window=7) if "vs_fpm" in df.columns else pd.Series(np.zeros(n))
    baro   = _smooth(df["baro_alt_ft"].fillna(0), window=5) if "baro_alt_ft" in df.columns else pd.Series(np.zeros(n))
    power  = _smooth(df["power_pct"].fillna(0),   window=5) if "power_pct" in df.columns else pd.Series(np.zeros(n))
    oil_t  = _smooth(df["oil_temp_f"].fillna(0),  window=11) if "oil_temp_f" in df.columns else pd.Series(np.zeros(n))

    # AGL approximation (baro alt − field elevation)
    agl    = baro - field_elev_ft

    # ── State machine ─────────────────────────────────────────────────────────
    phases = [Phase.UNKNOWN] * n
    state  = Phase.PRE_START
    dwell  = 0   # seconds in current candidate state

    def transition(new_state, i):
        nonlocal state, dwell
        if verbose and new_state != state:
            t = df["datetime"].iloc[i] if "datetime" in df.columns else i
            print(f"  {t}  {state.value} → {new_state.value}")
        state = new_state
        dwell = 0

    for i in range(n):
        r = rpm.iloc[i]
        v = ias.iloc[i]
        s = vs.iloc[i]
        a = agl.iloc[i]
        p = power.iloc[i]
        o = oil_t.iloc[i]
        dwell += 1

        if state == Phase.PRE_START:
            if r > 500:
                transition(Phase.ENGINE_START, i)

        elif state == Phase.ENGINE_START:
            if r > 1500 and r < 3000 and v < 10:
                transition(Phase.WARMUP, i)

        elif state == Phase.WARMUP:
            # Exit warmup when: oil is warm enough OR aircraft starts moving
            if v > 5:
                transition(Phase.TAXI, i)
            elif o >= warmup_oil_target_f and r > 1500 and v < 5:
                # Still on ground, warmed up — stay warmup until we taxi
                pass
            elif r < 500:
                transition(Phase.SHUTDOWN, i)

        elif state == Phase.TAXI:
            if r > 4500 and v < 35 and a < 50:
                transition(Phase.TAKEOFF_ROLL, i)
            elif r < 500:
                transition(Phase.SHUTDOWN, i)
            elif r < 2000 and v < 5:
                transition(Phase.WARMUP, i)

        elif state == Phase.TAKEOFF_ROLL:
            if v > 50 and s > 200:
                transition(Phase.CLIMB, i)
            elif r < 3000 and v < 20:
                transition(Phase.TAXI, i)

        elif state == Phase.CLIMB:
            # Require meaningful altitude gain above the departure field
            # before APPROACH becomes reachable — right after rotation,
            # AGL is still low by definition and should not be read as
            # "returning to land."
            climbed_clear_of_pattern = a > 800

            if s < min_cruise_vs_fpm and s > -min_cruise_vs_fpm and v > 60:
                dwell += 1
                if dwell >= min_cruise_duration_s:
                    transition(Phase.CRUISE, i)
            elif s < -cruise_exit_vs_fpm:
                transition(Phase.DESCENT, i)
            elif r < 2000 and v < 20:
                transition(Phase.LANDING_ROLL, i)
            elif climbed_clear_of_pattern and a < 500 and v < 90:
                transition(Phase.APPROACH, i)
            else:
                dwell = 0

        elif state == Phase.CRUISE:
            # Exit thresholds are wider than the entry threshold (hysteresis)
            # so ordinary VS noise around min_cruise_vs_fpm doesn't cause
            # rapid CRUISE/CLIMB/DESCENT flicker. A brief excursion must
            # also persist for a couple seconds, not just touch the line once.
            if s > cruise_exit_vs_fpm:
                dwell += 1
                if dwell >= 3:
                    transition(Phase.CLIMB, i)
            elif s < -cruise_exit_vs_fpm:
                dwell += 1
                if dwell >= 3:
                    transition(Phase.DESCENT, i)
            else:
                dwell = 0
            if a < 1000 and v < 85:
                transition(Phase.APPROACH, i)

        elif state == Phase.DESCENT:
            if s > cruise_exit_vs_fpm:
                transition(Phase.CLIMB, i)
            elif s > -min_cruise_vs_fpm / 2 and s < min_cruise_vs_fpm and v > 60:
                dwell += 1
                if dwell >= 45:
                    transition(Phase.CRUISE, i)
            elif a < 1500 and v < 100:
                transition(Phase.APPROACH, i)
            elif r < 2000 and v < 30 and a < 100:
                transition(Phase.LANDING_ROLL, i)
            else:
                dwell = 0

        elif state == Phase.APPROACH:
            if r < 2000 and v < 30 and a < 50:
                transition(Phase.LANDING_ROLL, i)
            elif s > 400:
                transition(Phase.CLIMB, i)
            elif s < -min_cruise_vs_fpm and a > 2000:
                transition(Phase.DESCENT, i)

        elif state == Phase.LANDING_ROLL:
            if v < 5 and r < 2500:
                transition(Phase.TAXI, i)
            elif r < 500:
                transition(Phase.SHUTDOWN, i)

        elif state == Phase.SHUTDOWN:
            if r > 500:
                transition(Phase.ENGINE_START, i)

        phases[i] = state

    df["phase"] = [p.value for p in phases]

    # Mark rows where phase changes
    phase_s = pd.Series(df["phase"].values, index=df.index)
    df["phase_changed"] = phase_s != phase_s.shift(1)

    return df


# ── Phase summary ─────────────────────────────────────────────────────────────

def phase_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a summary table of phases: start time, end time, duration,
    and key engine stats per phase.
    """
    if "phase" not in df.columns:
        raise ValueError("Run detect_phases() first.")

    records = []
    groups = df.groupby((df["phase"] != df["phase"].shift()).cumsum())
    for _, g in groups:
        phase_name = g["phase"].iloc[0]
        t_start    = g["datetime"].iloc[0]
        t_end      = g["datetime"].iloc[-1]
        dur_s      = (t_end - t_start).total_seconds() + 1

        rec = {
            "phase":      phase_name,
            "start":      t_start,
            "end":        t_end,
            "duration_s": dur_s,
            "rows":       len(g),
        }

        for col, stat, label in [
            ("rpm",           "mean", "rpm_mean"),
            ("rpm",           "max",  "rpm_max"),
            ("power_pct",     "mean", "power_pct_mean"),
            ("power_pct",     "max",  "power_pct_max"),
            ("ias_kt",        "mean", "ias_kt_mean"),
            ("fuel_flow_gph", "mean", "fuel_flow_gph_mean"),
            ("oil_temp_f",    "max",  "oil_temp_f_max"),
            ("coolant_temp_f","max",  "coolant_temp_f_max"),
            ("egt_max_f",     "max",  "egt_max_f"),
            ("egt_spread_f",  "max",  "egt_spread_f_max"),
        ]:
            if col in g.columns:
                val = getattr(g[col].dropna(), stat)()
                rec[label] = round(float(val), 1) if not pd.isna(val) else None

        records.append(rec)

    return pd.DataFrame(records)


def overboost_time(
    df: pd.DataFrame,
    engine_config: Optional[dict] = None,
) -> dict:
    """
    Return overboost statistics for a flight.
    Thresholds read from engine config (overboost block) so the same
    function works correctly for any Rotax iS engine.
    """
    if "rpm" not in df.columns:
        return {}

    if engine_config is None:
        from .limits import load_engine_config
        engine_config = load_engine_config()

    ob_cfg        = engine_config.get("overboost", {})
    rpm_threshold = ob_cfg.get("rpm_threshold", 5500)
    pwr_threshold = ob_cfg.get("power_pct_threshold", 100)
    time_limit_s  = ob_cfg.get("time_limit_s", 300)

    ob_mask = (df["rpm"] > rpm_threshold) | (df["power_pct"].fillna(0) > pwr_threshold)
    ob_rows = ob_mask.sum()

    max_block = 0
    block = 0
    for val in ob_mask:
        if val:
            block += 1
            max_block = max(max_block, block)
        else:
            block = 0

    return {
        "overboost_total_s":    int(ob_rows),
        "overboost_max_block_s": int(max_block),
        "overboost_limit_s":    time_limit_s,
        "overboost_exceeded":   max_block > time_limit_s,
    }
