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
