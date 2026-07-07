"""
cas.py — CAS alert parser for G3X logs.

The G3X 'CAS Alert' column is a composite string of all active
annunciations delimited by ' / '. This module parses, counts,
and analyses alert persistence — particularly the 'ENGINE ECU' alert
which is a priority investigation item.

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

# ── ENGINE ECU classifier constants ──────────────────────────────────────────
_RPM_RUNNING               = 500
_VOLTAGE_DECLINE_THRESHOLD = 0.5   # V drop over run → SHUTDOWN
_LANE_CHECK_MAX_IAS_KT     = 20
_LANE_CHECK_PAIR_WINDOW_S  = 90

# Known alert categories for 916iS / G3X installation
ALERT_SEVERITY = {
    "ENGINE ECU":           "WARNING",   # FADEC fault — investigate with BUDS
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

# Alerts that are EXPECTED at powerup and should clear after engine start
POWERUP_TRANSIENT = {"SET BARO", "EFIS ON BKUP", "NAV ON BKUP", "ARM BKUP"}

# Alerts that are NEVER expected during normal flight
ALWAYS_ABNORMAL = {"ENGINE ECU", "OIL PRESS", "ALT FAIL", "EARTH X FAIL", "FPCM FAULT"}


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
        pre = " [POWERUP]" if self.started_before_engine else ""
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

    # Specific ENGINE ECU analysis
    if "ENGINE ECU" in by_alert:
        lines.append("")
        p = alert_persistence(df, "ENGINE ECU")
        lines.append(f"  ENGINE ECU persistence: {p['pct_of_flight']:.0f}% of log rows")
        lines.append(f"  Present before engine start: {p['present_before_engine']}")
        lines.append(f"  Present entire flight: {p['present_entire_flight']}")
        lines.append("  → Action required: Pull B.U.D.S. fault log at next maintenance.")
        lines.append("  → Check G3X Config mode (on ground, engine running) for fault code.")

    return "\n".join(lines)

def classify_engine_ecu_run(
    df: pd.DataFrame,
    start_idx: int,
    end_idx: int,
    engine_config: Optional[dict] = None,
) -> str:
    """
    Classify a single ENGINE ECU run into one of four categories:
    POWERUP | SHUTDOWN | LANE_CHECK | IN_FLIGHT

    Parameters
    ----------
    df : pd.DataFrame
        Full flight dataframe (not sliced).
    start_idx, end_idx : int
        Row indices of the run within df.
    engine_config : dict, optional
        Engine config from load_engine_config(). If None, loads default.

    Returns
    -------
    str — one of POWERUP, SHUTDOWN, LANE_CHECK, IN_FLIGHT
    """
    if engine_config is None:
        from .limits import load_engine_config
        engine_config = load_engine_config()

    phase_cfg = engine_config.get("phase_detection", {})
    lane_check_max_duration_s = phase_cfg.get("lane_check_max_duration_s", 15)
    lane_check_rpm_min        = phase_cfg.get("runup_rpm_min", 3000)
    lane_check_rpm_max        = phase_cfg.get("runup_rpm_max", 5000)

    seg        = df.loc[start_idx:end_idx]
    rpm_vals   = seg["rpm"].fillna(0)
    engine_rows = (rpm_vals > _RPM_RUNNING).sum()
    total_rows  = len(seg)
    dur_s       = total_rows  # 1-second logging

    # ── POWERUP / SHUTDOWN ────────────────────────────────────────────────────
    if engine_rows / max(total_rows, 1) < 0.3:
        if "main_volts" in seg.columns:
            volts = seg["main_volts"].dropna()
            if len(volts) >= 3:
                if volts.iloc[:3].mean() > volts.iloc[-3:].mean() + _VOLTAGE_DECLINE_THRESHOLD:
                    return "SHUTDOWN"
        return "POWERUP"

    # ── LANE_CHECK ────────────────────────────────────────────────────────────
    mean_rpm = float(rpm_vals[rpm_vals > _RPM_RUNNING].mean()) if engine_rows else 0
    mean_ias = float(seg["ias_kt"].fillna(0).mean()) if "ias_kt" in seg.columns else 99

    if (dur_s <= lane_check_max_duration_s
            and lane_check_rpm_min <= mean_rpm <= lane_check_rpm_max
            and mean_ias <= _LANE_CHECK_MAX_IAS_KT):
        return "LANE_CHECK"

    # ── Final gate: reject likely shutdown/taxi events ────────────────────────
    # A run with low IAS, low-medium RPM, and long duration is almost certainly
    # a shutdown or taxi event misclassified as in-flight.
    if (mean_ias <= _LANE_CHECK_MAX_IAS_KT
            and mean_rpm < lane_check_rpm_min
            and dur_s > 30):
        return "SHUTDOWN"

    return "IN_FLIGHT"


def extract_engine_ecu_runs(
    df: pd.DataFrame,
    engine_config: Optional[dict] = None,
) -> list[dict]:
    """
    Find all ENGINE ECU runs in a flight dataframe and return a list of
    dicts with classification, timestamps, duration, co-active alerts,
    and oil pressure NaN fraction.

    Parameters
    ----------
    df : pd.DataFrame
        Full flight dataframe with cas_alert column.
    engine_config : dict, optional
        Engine config from load_engine_config(). If None, loads default.

    Returns
    -------
    list[dict] with keys:
        source_file, date, start_time, end_time, duration_s,
        classification, co_alerts, oil_nan_frac,
        start_idx, end_idx, mean_rpm, mean_ias_kt
    """
    if engine_config is None:
        from .limits import load_engine_config
        engine_config = load_engine_config()

    if "cas_alert" not in df.columns:
        return []

    ecu_active = df["cas_alert"].apply(lambda v: "ENGINE ECU" in _split_cas(v))
    runs = []

    in_run    = False
    start_idx = None

    for idx in range(len(df)):
        active = bool(ecu_active.iloc[idx])
        if active and not in_run:
            in_run    = True
            start_idx = df.index[idx]
        elif not active and in_run:
            end_idx = df.index[idx - 1]
            in_run  = False
            runs.append((start_idx, end_idx))

    if in_run and start_idx is not None:
        runs.append((start_idx, df.index[-1]))

    results = []
    fname   = df["_source_file"].iloc[0] if "_source_file" in df.columns else ""
    date    = df["datetime"].iloc[0].date() if "datetime" in df.columns else None

    for start_idx, end_idx in runs:
        seg           = df.loc[start_idx:end_idx]
        classification = classify_engine_ecu_run(df, start_idx, end_idx, engine_config)
        dur_s         = len(seg)

        # Co-active alerts (excluding ENGINE ECU itself)
        co_alerts: list[str] = []
        for cas_val in seg["cas_alert"].dropna():
            for alert in _split_cas(cas_val):
                if alert and alert != "ENGINE ECU" and alert not in co_alerts:
                    co_alerts.append(alert)

        # Oil pressure NaN fraction
        oil_nan_frac = None
        if "oil_press_psi" in seg.columns:
            oil_nan_frac = float(seg["oil_press_psi"].isna().mean())

        results.append({
            "source_file":     fname,
            "date":            date,
            "start_time":      df.loc[start_idx, "datetime"] if "datetime" in df.columns else None,
            "end_time":        df.loc[end_idx,   "datetime"] if "datetime" in df.columns else None,
            "duration_s":      dur_s,
            "classification":  classification,
            "co_alerts":       co_alerts,
            "oil_nan_frac":    oil_nan_frac,
            "start_idx":       start_idx,
            "end_idx":         end_idx,
            "mean_rpm":        float(seg["rpm"].fillna(0).mean()) if "rpm" in seg.columns else None,
            "mean_ias_kt":     float(seg["ias_kt"].fillna(0).mean()) if "ias_kt" in seg.columns else None,
        })

        # ── Lane check pairing ────────────────────────────────────────────────────
        # Mark LANE_CHECK runs that occur in pairs within the pairing window
        # (one run per lane, both within _LANE_CHECK_PAIR_WINDOW_S seconds)
        lc_indices = [
            i for i, r in enumerate(results)
            if r["classification"] == "LANE_CHECK"
        ]
        paired = set()
        for i in range(len(lc_indices)):
            for j in range(i + 1, len(lc_indices)):
                ri = results[lc_indices[i]]
                rj = results[lc_indices[j]]
                if (ri["start_time"] is not None and rj["start_time"] is not None):
                    gap = abs((rj["start_time"] - ri["start_time"]).total_seconds())
                    if gap <= _LANE_CHECK_PAIR_WINDOW_S:
                        paired.add(lc_indices[i])
                        paired.add(lc_indices[j])

        for i, r in enumerate(results):
            r["lane_check_pair"] = (i in paired)
            r["lane_check_note"] = "paired" if (i in paired and r["classification"] == "LANE_CHECK") else ""

    return results