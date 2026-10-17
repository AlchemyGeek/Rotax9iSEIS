"""
cas.py — CAS alert parser for G3X logs.

The G3X 'CAS Alert' column is a composite string of all active
annunciations delimited by ' / '. This module parses, counts,
and analyses alert persistence — particularly the 'ENGINE ECU' alert
whose meaning depends on the flight phase it occurs in.

Usage
-----
    from slingology_eis.cas import parse_cas, cas_report

    alerts = parse_cas(df)
    print(cas_report(df))
"""

from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
import pandas as pd
from typing import Optional
import numpy as np

# Known alert categories for 916iS / G3X installation
ALERT_SEVERITY = {
    "ENGINE ECU":           "WARNING",   # FADEC lane/communication alert; meaning depends on phase (§8.6)
    "OIL PRESS":            "WARNING",
    "FUEL PRESS":           "CAUTION",
    "CHECK FUEL":           "CAUTION",
    "ALT FAIL":             "WARNING",
    "EARTH X FAIL":         "WARNING",
    "FPCM FAULT":           "CAUTION",
    "EFIS ON BKUP":         "CAUTION",   # EFIS running on backup avionics bus
    "NAV ON BKUP":          "CAUTION",   # NAV running on backup bus
    "ARM BKUP":             "CAUTION",
    "RAGL FAIL":            "CAUTION",   # Radar altimeter fail
    "TRAFFIC FAIL":         "ADVISORY",
    "SET BARO":             "ADVISORY",
    "CO PPM":               "CAUTION",
}

# Alerts that are EXPECTED at avionics power-on and should clear after engine start
STARTUP_TRANSIENT = {"SET BARO", "EFIS ON BKUP", "NAV ON BKUP", "ARM BKUP"}

# Alerts that are NEVER expected during normal flight. ENGINE ECU is not
# one: whether it matters depends on the flight phase it occurs in, which
# its classification decides (Spec 01 §8.6).
ALWAYS_ABNORMAL = {"OIL PRESS", "ALT FAIL", "EARTH X FAIL", "FPCM FAULT"}


@dataclass
class AlertEvent:
    alert: str
    severity: str
    started_at: pd.Timestamp
    ended_at: pd.Timestamp
    duration_s: float
    rows: int
    started_before_engine: bool    # True if present before RPM > 0

    def __str__(self):
        pre = " [before engine start]" if self.started_before_engine else ""
        return (
            f"[{self.severity}] {self.alert}{pre}  "
            f"at {self.started_at:%H:%M:%S}  "
            f"for {self.duration_s:.0f}s"
        )


def _split_cas(cas_str) -> list[str]:
    """Split a CAS composite string into individual alert tokens."""
    if pd.isna(cas_str) or str(cas_str).strip() == "":
        return []
    return [a.strip() for a in str(cas_str).split("/") if a.strip()]


def parse_cas(df: pd.DataFrame) -> list[AlertEvent]:
    """
    Parse the CAS Alert column into a list of AlertEvent objects.

    Each contiguous run of the same alert is one event.
    """
    if "cas_alert" not in df.columns:
        return []

    # Expand: one boolean column per unique alert token
    all_alerts: set[str] = set()
    for val in df["cas_alert"].dropna():
        all_alerts.update(_split_cas(val))

    if not all_alerts:
        return []

    # Determine if engine is running at each row
    engine_on = (df["rpm"].fillna(0) > 500) if "rpm" in df.columns \
        else pd.Series(False, index=df.index)

    events: list[AlertEvent] = []

    for alert in sorted(all_alerts):
        # Build presence mask
        mask = df["cas_alert"].apply(lambda v: alert in _split_cas(v))

        in_event = False
        start_idx = None

        for i in range(len(mask)):
            if mask.iloc[i] and not in_event:
                in_event = True
                start_idx = i
            elif not mask.iloc[i] and in_event:
                in_event = False
                _add_alert_event(df, alert, start_idx, i - 1,
                                 engine_on, events)
        if in_event and start_idx is not None:
            _add_alert_event(df, alert, start_idx, len(mask) - 1,
                             engine_on, events)

    events.sort(key=lambda e: e.started_at)
    return events


def _add_alert_event(df, alert, start_idx, end_idx, engine_on, events):
    t_start = df["datetime"].iloc[start_idx]
    t_end   = df["datetime"].iloc[end_idx]
    dur_s   = (t_end - t_start).total_seconds() + 1
    severity = ALERT_SEVERITY.get(alert, "ADVISORY")
    before_engine = not engine_on.iloc[start_idx]

    events.append(AlertEvent(
        alert=alert,
        severity=severity,
        started_at=t_start,
        ended_at=t_end,
        duration_s=dur_s,
        rows=end_idx - start_idx + 1,
        started_before_engine=before_engine,
    ))


def alert_persistence(
    df: pd.DataFrame,
    alert: str,
) -> dict:
    """
    Detailed persistence analysis for a specific alert.

    Returns fraction of flight rows where alert is active,
    first and last occurrence, whether it appeared before engine start.
    """
    if "cas_alert" not in df.columns:
        return {}

    mask = df["cas_alert"].apply(lambda v: alert in _split_cas(v))
    active_rows  = mask.sum()
    total_rows   = len(df)
    engine_rows  = (df["rpm"].fillna(0) > 500).sum() if "rpm" in df.columns else 0

    first_idx = mask.idxmax() if mask.any() else None
    last_idx  = mask[::-1].idxmax() if mask.any() else None

    engine_on_at_first = (
        df["rpm"].iloc[first_idx] > 500
        if first_idx is not None and "rpm" in df.columns else None
    )

    return {
        "alert":                 alert,
        "active_rows":           int(active_rows),
        "total_rows":            total_rows,
        "pct_of_flight":         round(active_rows / total_rows * 100, 1) if total_rows else 0,
        "pct_of_engine_running": round(active_rows / engine_rows * 100, 1) if engine_rows else 0,
        "first_occurrence":      df["datetime"].iloc[first_idx] if first_idx is not None else None,
        "last_occurrence":       df["datetime"].iloc[last_idx]  if last_idx is not None else None,
        "present_before_engine": not bool(engine_on_at_first) if engine_on_at_first is not None else None,
        "present_entire_flight": bool(active_rows == total_rows),
    }


def cas_report(df: pd.DataFrame) -> str:
    """Return a formatted CAS alert summary for one flight."""
    events = parse_cas(df)
    lines  = ["── CAS Alerts ─────────────────────────────────────"]

    if not events:
        lines.append("  No CAS alerts in this log.")
        return "\n".join(lines)

    # Unique alerts and their total active time
    by_alert: dict[str, list[AlertEvent]] = {}
    for e in events:
        by_alert.setdefault(e.alert, []).append(e)

    for alert, alert_events in sorted(by_alert.items()):
        total_s = sum(e.duration_s for e in alert_events)
        sev     = alert_events[0].severity
        pre_eng = any(e.started_before_engine for e in alert_events)
        flag    = "⚡" if alert in ALWAYS_ABNORMAL else ("⚠" if pre_eng else "·")

        lines.append(
            f"  {flag} [{sev}] {alert}  "
            f"{len(alert_events)} run(s)  total {total_s:.0f}s"
            + ("  [started before engine]" if pre_eng else "")
        )

    # ENGINE ECU by flight phase (Spec 01 §8.6)
    if "ENGINE ECU" in by_alert:
        ext = extract_engine_ecu_runs(df)
        counts = Counter(r["classification"] for r in ext.runs)
        lines.append("")
        lines.append("  ENGINE ECU by phase: " + "  ".join(f"{c}:{counts.get(c, 0)}" for c in ECU_CLASSES)
                     + f"  (sub-threshold blips: {ext.sub_threshold_blips}, lane check: {ext.lane_check})")

    return "\n".join(lines)

def ecu_active_series(df: pd.DataFrame) -> pd.Series:
    """Boolean Series: True on rows where 'ENGINE ECU' is an active CAS alert."""
    return df["cas_alert"].apply(lambda v: "ENGINE ECU" in _split_cas(v))


# ── ENGINE ECU classification (Spec 01 §8.6, v0.19) ──────────────────────────
# Classification is by the flight phase the run overlaps — phases.py's
# output is the only ground/flight input. The lane-check signature is the
# one non-phase test kept, because it is what separates a deliberate
# single-lane run-up from any other ground event.

ECU_CLASSES = ("GROUND_START", "LANE_CHECK", "GROUND", "IN_FLIGHT", "GROUND_SHUTDOWN")

# Spec 01 §8.6 (v0.21): classified CAS alerts — the ones whose GROUND /
# IN_FLIGHT runs become events, filter targets and Trends panels. Today
# only ENGINE ECU; others join through Spec 10 §8.
CLASSIFIED_CAS_IDS = ("ENGINE ECU",)
CAS_EVENT_CLASSES = ("GROUND", "IN_FLIGHT")

_PHASE_CLASS = {
    "PRE_START": "GROUND_START", "ENGINE_START": "GROUND_START", "WARMUP": "GROUND_START",
    "TAXI": "GROUND",
    "TAKEOFF_ROLL": "IN_FLIGHT", "CLIMB": "IN_FLIGHT", "CRUISE": "IN_FLIGHT",
    "DESCENT": "IN_FLIGHT", "APPROACH": "IN_FLIGHT", "LANDING_ROLL": "IN_FLIGHT",
    "SHUTDOWN": "GROUND_SHUTDOWN",
}
# LANDING_ROLL after ground speed has dropped below this is the aircraft
# taxiing off the runway — GROUND, not IN_FLIGHT (§8.6 table).
_LANDING_ROLL_GROUND_KT = 5
# Finding-9 guard (§8.6): the phase detector's own on-ground IAS ceiling,
# so the guard and the detector agree on what "taxi speed" means.
from .phases import _ON_GROUND_IAS_KT as TAXI_IAS_CEILING_KT  # noqa: E402

_LANE_CHECK_PHASES = {"WARMUP", "TAXI"}
_LANE_CHECK_MAX_IAS_KT = 20          # "stationary"
_LANE_CHECK_PAIR_WINDOW_S = 90
_RPM_RUNNING = 500

_DEFAULT_MERGE_GAP_S = 5
_DEFAULT_MIN_EVENT_DURATION_S = 3


_TAKEOFF_NOT_DETECTED_THRESHOLD_ROWS = 180  # 3 minutes at 1 Hz


def takeoff_not_detected(df: pd.DataFrame) -> tuple[bool, int]:
    """(flag, airborne_rows) for the PHASE_TAKEOFF_NOT_DETECTED quality
    warning (finding 9): more than 3 minutes of airborne-looking rows (rpm
    > 3000 and IAS > 30 kt) with no TAKEOFF_ROLL or CLIMB phase labelled.
    One definition, shared by analyze_flight's warning, the ENGINE ECU
    finding-9 guard and the per-flight ECU metrics."""
    if "rpm" in df.columns and "ias_kt" in df.columns:
        airborne_rows = int(((df["rpm"].fillna(0) > 3000) & (df["ias_kt"].fillna(0) > 30)).sum())
    else:
        airborne_rows = 0
    phases = set(df["phase"].unique()) if "phase" in df.columns else set()
    flag = (airborne_rows > _TAKEOFF_NOT_DETECTED_THRESHOLD_ROWS
            and "TAKEOFF_ROLL" not in phases and "CLIMB" not in phases)
    return flag, airborne_rows


@dataclass
class EcuExtraction:
    """One flight's ENGINE ECU runs (classified, ≥ min duration), how many
    shorter runs were dropped (data quality only), and its lane check."""
    runs: list[dict]
    sub_threshold_blips: int
    lane_check: str   # "both" | "single" | "none"


def _seg_mean(seg: pd.DataFrame, col: str) -> Optional[float]:
    if col not in seg.columns:
        return None
    v = seg[col].mean()  # skips NaN by default — see the call site's note
    return float(v) if pd.notna(v) else None


def _raw_runs(active: pd.Series) -> list[tuple[int, int]]:
    """(first, last) positional row of each contiguous active stretch."""
    runs, start = [], None
    vals = active.to_numpy()
    for i, a in enumerate(vals):
        if a and start is None:
            start = i
        elif not a and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(vals) - 1))
    return runs


def _merge_runs(runs: list[tuple[int, int]], times: pd.Series, merge_gap_s: float) -> list[tuple[int, int]]:
    """Merge runs whose separation (next start − previous end, in seconds)
    is less than merge_gap_s."""
    merged: list[tuple[int, int]] = []
    for a, b in runs:
        if merged and (times.iloc[a] - times.iloc[merged[-1][1]]).total_seconds() < merge_gap_s:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def _known_phases(phase: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Each row's phase with UNKNOWN replaced by the nearest preceding known
    phase (the following one if nothing precedes it), and a mask of the
    rows that were substituted."""
    unknown = phase.isna() | (phase == "UNKNOWN")
    known = phase.where(~unknown).ffill().bfill()
    return known.fillna("UNKNOWN"), unknown


def _row_class(phase: str, gnd_spd_kt) -> str:
    if phase == "LANDING_ROLL" and gnd_spd_kt is not None and pd.notna(gnd_spd_kt) and gnd_spd_kt < _LANDING_ROLL_GROUND_KT:
        return "GROUND"
    return _PHASE_CLASS.get(phase, "GROUND")


def classify_ecu_run(
    seg: pd.DataFrame,
    known_phase: pd.Series,
    substituted: pd.Series,
    min_event_duration_s: float,
    lane_check_max_duration_s: float,
    runup_rpm_min: float,
    runup_rpm_max: float,
    takeoff_not_detected: bool = False,
    engine_ran_before: bool = True,
) -> tuple[str, str, bool]:
    """(classification, deciding phase, phase_uncertain) for one run.

    Rules in order (Spec 01 §8.6 v0.20):
    1. Engine state. If the engine stops during the run (RPM drops to or
       below the running threshold, a missing reading counting as stopped)
       and stays stopped to the run's end, it is GROUND_SHUTDOWN, whatever
       the phase labels — unless the aircraft is above taxi IAS while
       stopped, which is not a shutdown on the ground. A run wholly before
       the engine first runs in this log is GROUND_START.
    2. IN_FLIGHT wins when ≥ min_event_duration_s rows are in an in-flight
       phase with IAS above the taxi ceiling.
    3. Otherwise the class holding the majority of its rows (ties go to the
       class reached first in the run); a WARMUP/TAXI run with the
       lane-check signature is LANE_CHECK. Finding-9 guard: on a flight
       where takeoff wasn't detected, a GROUND run above taxi IAS is
       IN_FLIGHT, phase-uncertain.
    `engine_ran_before`: the engine ran at some row before this run's
    first row.
    """
    gs = seg["gnd_spd_kt"] if "gnd_spd_kt" in seg.columns else pd.Series([None] * len(seg), index=seg.index)
    ias_rows = seg["ias_kt"].fillna(0) if "ias_kt" in seg.columns else pd.Series(0.0, index=seg.index)
    row_classes = [_row_class(p, g) for p, g in zip(known_phase, gs)]
    uncertain = bool(substituted.any())
    running = (seg["rpm"].fillna(0) > _RPM_RUNNING).to_numpy() if "rpm" in seg.columns else np.zeros(len(seg), bool)

    # Rule 1 — engine state.
    if not running[-1]:
        idx = np.flatnonzero(running)
        tail_from = idx[-1] + 1 if len(idx) else 0
        stopped_in_run = len(idx) > 0 or engine_ran_before
        if stopped_in_run and float(ias_rows.iloc[tail_from:].max()) <= TAXI_IAS_CEILING_KT:
            return "GROUND_SHUTDOWN", str(known_phase.iloc[-1]), uncertain
        if not len(idx) and not engine_ran_before:
            # Wholly before the first running row — including a log in which
            # the engine never runs at all (avionics only).
            return "GROUND_START", Counter(known_phase).most_common(1)[0][0], uncertain

    # Rule 2 — IN_FLIGHT needs an in-flight phase *and* flying airspeed.
    n_flight = sum(1 for c, v in zip(row_classes, ias_rows) if c == "IN_FLIGHT" and v > TAXI_IAS_CEILING_KT)
    if n_flight >= min_event_duration_s:
        cls = "IN_FLIGHT"
    else:
        # Rule 3 — majority. An in-flight phase label at or below taxi
        # airspeed counts as GROUND here too: phase label alone never makes
        # a run IN_FLIGHT (the same reading as LANDING_ROLL < 5 kt above).
        row_classes = ["GROUND" if c == "IN_FLIGHT" and v <= TAXI_IAS_CEILING_KT else c
                       for c, v in zip(row_classes, ias_rows)]
        counts = Counter(row_classes)
        top = max(counts.values())
        cls = next(c for c in row_classes if counts[c] == top)

    phases_in_class = [p for p, c in zip(known_phase, row_classes) if c == cls]
    phase = Counter(phases_in_class).most_common(1)[0][0] if phases_in_class else known_phase.iloc[0]

    mean_rpm = _running_rpm_mean(seg)
    mean_ias = float(seg["ias_kt"].fillna(0).mean()) if "ias_kt" in seg.columns else 0.0

    if (cls != "IN_FLIGHT" and phase in _LANE_CHECK_PHASES
            and len(seg) <= lane_check_max_duration_s
            and runup_rpm_min <= mean_rpm <= runup_rpm_max
            and mean_ias <= _LANE_CHECK_MAX_IAS_KT):
        cls = "LANE_CHECK"

    if takeoff_not_detected and cls == "GROUND" and mean_ias > TAXI_IAS_CEILING_KT:
        cls, uncertain = "IN_FLIGHT", True

    return cls, phase, uncertain


def not_lane_check_reason(
    seg: pd.DataFrame, classification: str, phase: str,
    lane_check_max_duration_s: float, runup_rpm_min: float, runup_rpm_max: float,
) -> Optional[str]:
    """Spec 01 §8.6 (v0.21): why a GROUND run in WARMUP/TAXI is not a lane
    check, when it misses the signature on exactly one count —
    rpm_below_band / rpm_above_band / too_long / moving. None otherwise
    (two or more misses: it isn't close to a lane check). Pairing is not
    a reason: a lone in-band run is a LANE_CHECK (lane_check "single")."""
    if classification != "GROUND" or phase not in _LANE_CHECK_PHASES:
        return None
    rpm = _running_rpm_mean(seg)
    mean_ias = float(seg["ias_kt"].fillna(0).mean()) if "ias_kt" in seg.columns else 0.0
    misses = []
    if rpm < runup_rpm_min:
        misses.append("rpm_below_band")
    elif rpm > runup_rpm_max:
        misses.append("rpm_above_band")
    if len(seg) > lane_check_max_duration_s:
        misses.append("too_long")
    if mean_ias > _LANE_CHECK_MAX_IAS_KT:
        misses.append("moving")
    return misses[0] if len(misses) == 1 else None


def _running_rpm_mean(seg: pd.DataFrame) -> float:
    """Mean rpm over the run's engine-running rows (what a lane check is
    held at), 0 when the engine never ran in it."""
    rpm = seg["rpm"].fillna(0) if "rpm" in seg.columns else pd.Series(0, index=seg.index)
    running = rpm[rpm > _RPM_RUNNING]
    return float(running.mean()) if len(running) else 0.0


def extract_engine_ecu_runs(
    df: pd.DataFrame,
    engine_config: Optional[dict] = None,
    takeoff_not_detected: bool = False,
) -> EcuExtraction:
    """
    ENGINE ECU runs in one flight (Spec 01 §8.6): contiguous CAS rows,
    merged across gaps shorter than `cas.merge_gap_s`, kept as runs when
    at least `cas.min_event_duration_s` long (shorter ones are counted as
    `sub_threshold_blips`), each classified by the flight phase it
    overlaps. Needs `df["phase"]`; runs phase detection if it's missing.

    Each run dict carries: source_file, date, start_time, end_time,
    duration_s, classification, phase, phase_uncertain, co_alerts,
    oil_nan_frac, start_idx, end_idx, the per-run context means (mean_rpm,
    mean_ias_kt, mean_power_pct, mean_oil_press_psi, mean_oil_temp_f,
    mean_coolant_temp_f, mean_main_volts, mean_batt_amps,
    mean_fuel_press_psi, mean_baro_alt_ft), lane_check_pair and
    lane_check_note.
    """
    if engine_config is None:
        from .limits import load_engine_config
        engine_config = load_engine_config()
    if "cas_alert" not in df.columns:
        return EcuExtraction([], 0, "none")
    if "phase" not in df.columns:
        from .phases import detect_phases
        df = detect_phases(df.copy(), verbose=False)

    cas_cfg = engine_config.get("cas", {})
    merge_gap_s = cas_cfg.get("merge_gap_s", _DEFAULT_MERGE_GAP_S)
    min_dur_s = cas_cfg.get("min_event_duration_s", _DEFAULT_MIN_EVENT_DURATION_S)
    phase_cfg = engine_config.get("phase_detection", {})
    lc_max_s = phase_cfg.get("lane_check_max_duration_s", 15)
    rpm_min = phase_cfg.get("runup_rpm_min", 3000)
    rpm_max = phase_cfg.get("runup_rpm_max", 5000)
    pair_window_s = phase_cfg.get("lane_check_pair_window_s", _LANE_CHECK_PAIR_WINDOW_S)

    times = df["datetime"]
    known_phase, substituted = _known_phases(df["phase"])
    # Engine-state context for rule 1: did the engine run at any row before
    # each position?
    run_mask = (df["rpm"].fillna(0) > _RPM_RUNNING).to_numpy() if "rpm" in df.columns else np.zeros(len(df), bool)
    running_before = np.concatenate([[False], np.cumsum(run_mask)[:-1] > 0]) if len(df) else run_mask
    spans = _merge_runs(_raw_runs(ecu_active_series(df)), times, merge_gap_s)

    fname = df["_source_file"].iloc[0] if "_source_file" in df.columns else ""
    date = times.iloc[0].date()
    results, blips = [], 0
    for a, b in spans:
        dur_s = (times.iloc[b] - times.iloc[a]).total_seconds() + 1
        if dur_s < min_dur_s:
            blips += 1
            continue
        seg = df.iloc[a:b + 1]
        cls, phase, uncertain = classify_ecu_run(
            seg, known_phase.iloc[a:b + 1], substituted.iloc[a:b + 1],
            min_dur_s, lc_max_s, rpm_min, rpm_max, takeoff_not_detected,
            engine_ran_before=bool(running_before[a]),
        )
        co_alerts: list[str] = []
        for cas_val in seg["cas_alert"].dropna():
            for alert in _split_cas(cas_val):
                if alert != "ENGINE ECU" and alert not in co_alerts:
                    co_alerts.append(alert)
        results.append({
            "source_file":     fname,
            "date":            date,
            "start_time":      times.iloc[a],
            "end_time":        times.iloc[b],
            "duration_s":      dur_s,
            "classification":  cls,
            "phase":           phase,
            "phase_uncertain": uncertain,
            "not_lane_check_reason": not_lane_check_reason(seg, cls, phase, lc_max_s, rpm_min, rpm_max),
            "running_rpm":     round(_running_rpm_mean(seg), 1),
            "lane_check_band": {"rpm": (rpm_min + rpm_max) / 2, "tolerance": (rpm_max - rpm_min) / 2},
            "co_alerts":       co_alerts,
            "oil_nan_frac":    float(seg["oil_press_psi"].isna().mean()) if "oil_press_psi" in seg.columns else None,
            "start_idx":       df.index[a],
            "end_idx":         df.index[b],
            "mean_rpm":        float(seg["rpm"].fillna(0).mean()) if "rpm" in seg.columns else None,
            "mean_ias_kt":     float(seg["ias_kt"].fillna(0).mean()) if "ias_kt" in seg.columns else None,
            # skipna means, NOT the rpm/ias_kt fillna(0) convention above:
            # filling a gap in oil_press_psi with 0 would drag a healthy mean
            # toward the near-zero signature a co-alert check looks for.
            "mean_power_pct":       _seg_mean(seg, "power_pct"),
            "mean_oil_press_psi":   _seg_mean(seg, "oil_press_psi"),
            "mean_oil_temp_f":      _seg_mean(seg, "oil_temp_f"),
            "mean_coolant_temp_f":  _seg_mean(seg, "coolant_temp_f"),
            "mean_main_volts":      _seg_mean(seg, "main_volts"),
            "mean_batt_amps":       _seg_mean(seg, "batt_amps"),
            "mean_fuel_press_psi":  _seg_mean(seg, "fuel_press_psi"),
            "mean_baro_alt_ft":     _seg_mean(seg, "baro_alt_ft"),
        })

    # Lane-check pairing: one run per lane, both within the pairing window.
    lc = [i for i, r in enumerate(results) if r["classification"] == "LANE_CHECK"]
    paired: set[int] = set()
    for x in range(len(lc)):
        for y in range(x + 1, len(lc)):
            gap = abs((results[lc[y]]["start_time"] - results[lc[x]]["start_time"]).total_seconds())
            if gap <= pair_window_s:
                paired.update((lc[x], lc[y]))
    for i, r in enumerate(results):
        r["lane_check_pair"] = i in paired
        r["lane_check_note"] = "paired" if i in paired else ""

    lane_check = "both" if paired else ("single" if lc else "none")
    return EcuExtraction(results, blips, lane_check)
