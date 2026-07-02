"""
loader.py — Garmin G3X EIS log parser and normaliser.

Loads one or more G3X CSV files into typed, normalised DataFrames.
Handles the two-row header format (row 0: airframe metadata,
row 1: column names, row 2+: 1-second data records).

Usage
-----
    from slingology_eis.loader import load_log, load_directory

    df = load_log("data/logs/log_20260518_195524_KAWO.csv")
    all_flights = load_directory("data/logs/")
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np


# ── Column renaming: G3X names → short aliases ───────────────────────────────

COLUMN_MAP = {
    "Date (yyyy-mm-dd)":          "date",
    "Time (hh:mm:ss)":            "time",
    "UTC Time (hh:mm:ss)":        "utc_time",
    "UTC Offset (hh:mm)":         "utc_offset",
    "Latitude (deg)":             "lat",
    "Longitude (deg)":            "lon",
    "GPS Altitude (ft)":          "gps_alt_ft",
    "GPS Ground Speed (kt)":      "gnd_spd_kt",
    "GPS Ground Track (deg)":     "track_deg",
    "Pressure Altitude (ft)":     "press_alt_ft",
    "Baro Altitude (ft)":         "baro_alt_ft",
    "Vertical Speed (ft/min)":    "vs_fpm",
    "Indicated Airspeed (kt)":    "ias_kt",
    "True Airspeed (kt)":         "tas_kt",
    "Pitch (deg)":                "pitch_deg",
    "Roll (deg)":                 "roll_deg",
    "Lateral Acceleration (G)":   "lat_g",
    "Normal Acceleration (G)":    "norm_g",
    "AOA Cp":                     "aoa_cp",
    "AOA":                        "aoa",
    "Outside Air Temp (deg C)":   "oat_c",
    "Density Altitude (ft)":      "da_ft",
    "Baro Setting (inch Hg)":     "baro_inhg",
    "Wind Speed (kt)":            "wind_spd_kt",
    "Wind Direction (deg)":       "wind_dir_deg",
    # ── Engine parameters ──────────────────────────────────────────────────────
    "RPM":                        "rpm",
    "Engine Power (%)":           "power_pct",
    "Manifold Press (inch Hg)":   "map_inhg",
    "Oil Press (PSI)":            "oil_press_psi",
    "Oil Temp (deg F)":           "oil_temp_f",
    "Coolant Temp (deg F)":       "coolant_temp_f",
    "Fuel Qty L (gal)":           "fuel_qty_l_gal",
    "Fuel Qty R (gal)":           "fuel_qty_r_gal",
    "Fuel Flow (gal/hour)":       "fuel_flow_gph",
    "Fuel Press (PSI)":           "fuel_press_psi",
    "EGT1 (deg F)":               "egt1_f",
    "EGT2 (deg F)":               "egt2_f",
    "EGT3 (deg F)":               "egt3_f",
    "EGT4 (deg F)":               "egt4_f",
    "Flap Position":              "flap_pos",
    "Elevator Trim":              "elev_trim",
    "Efis Bkup Volts":            "efis_bkup_v",
    "Nav Bkup Volts":             "nav_bkup_v",
    "Main Volts":                 "main_volts",
    "Batt Amps":                  "batt_amps",
    "Co Ppm":                     "co_ppm",
    # ── Discrete channels ─────────────────────────────────────────────────────
    "EFIS ON BKUP (discrete)":    "efis_on_bkup",
    "NAV ON BKUP (discrete)":     "nav_on_bkup",
    "ARM BKUP (discrete)":        "arm_bkup",
    "PITOT HEAT (discrete)":      "pitot_heat",
    "FPCM FAULT (discrete)":      "fpcm_fault",
    "CHECK FUEL (discrete)":      "check_fuel",
    "ALT FAIL (discrete)":        "alt_fail",
    "EARTH X FAIL (discrete)":    "earth_x_fail",
    "CAS Alert":                  "cas_alert",
    "Terrain Alert":              "terrain_alert",
    "Autopilot State":            "ap_state",
    "Active Nav Source":          "nav_source",
    "Network Status":             "network_status",
}

# Numeric columns (attempt float conversion)
NUMERIC_COLS = [
    "lat", "lon", "gps_alt_ft", "gnd_spd_kt", "track_deg",
    "press_alt_ft", "baro_alt_ft", "vs_fpm", "ias_kt", "tas_kt",
    "pitch_deg", "roll_deg", "lat_g", "norm_g", "aoa_cp", "aoa",
    "oat_c", "da_ft", "baro_inhg", "wind_spd_kt", "wind_dir_deg",
    "rpm", "power_pct", "map_inhg", "oil_press_psi", "oil_temp_f",
    "coolant_temp_f", "fuel_qty_l_gal", "fuel_qty_r_gal",
    "fuel_flow_gph", "fuel_press_psi",
    "egt1_f", "egt2_f", "egt3_f", "egt4_f",
    "main_volts", "batt_amps", "co_ppm", "elev_trim",
    "efis_bkup_v", "nav_bkup_v", "flap_pos",
]

EGT_COLS   = ["egt1_f", "egt2_f", "egt3_f", "egt4_f"]
ENGINE_COLS = ["rpm", "power_pct", "map_inhg", "oil_press_psi", "oil_temp_f",
               "coolant_temp_f", "fuel_flow_gph", "fuel_press_psi"] + EGT_COLS


# ── Airframe metadata parser ──────────────────────────────────────────────────

@dataclass
class AirframeInfo:
    """Metadata from row 0 of the G3X CSV."""
    aircraft_ident: str = ""
    product: str = ""
    software_version: str = ""
    system_id: str = ""
    unit: str = ""
    airframe_hours: Optional[float] = None
    engine_hours: Optional[float] = None
    log_version: str = ""
    source_format: str = "unknown"   # "g3x_direct" | "garmin_pilot" | "unknown"
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_row(cls, row_text: str) -> "AirframeInfo":
        """Parse the metadata row into an AirframeInfo."""
        # Format: key="value", key="value", ...
        pairs = re.findall(r'(\w+)="([^"]*)"', row_text)
        d = {k: v for k, v in pairs}
        try:
            af_h = float(d.get("airframe_hours", "").replace(",", "."))
        except ValueError:
            af_h = None
        try:
            eng_h = float(d.get("engine_hours", "").replace(",", "."))
        except ValueError:
            eng_h = None
        return cls(
            aircraft_ident=d.get("aircraft_ident", ""),
            product=d.get("product", ""),
            software_version=d.get("software_version", ""),
            system_id=d.get("system_id", ""),
            unit=d.get("unit", ""),
            airframe_hours=af_h,
            engine_hours=eng_h,
            log_version=d.get("log_version", ""),
            raw=d,
        )
# ── Source format detection ────────────────────────────────────────────────────

def _detect_source_format(header_row: str) -> str:
    """
    Identify which export path produced this CSV.

    g3x_direct   — downloaded straight from the G3X SD card; header row
                   starts directly with 'Date (yyyy-mm-dd)'
    garmin_pilot — exported/shared via the Garmin Pilot app; header row
                   is prefixed with '#', e.g. '#Date (yyyy-mm-dd)'
    unknown      — neither pattern matched (flag for manual inspection
                   rather than silently guessing)
    """
    stripped = header_row.lstrip("\ufeff")  # tolerate a UTF-8 BOM from Excel re-saves
    if stripped.startswith("#Date"):
        return "garmin_pilot"
    if stripped.startswith("Date "):
        return "g3x_direct"
    return "unknown"


# ── Core loader ───────────────────────────────────────────────────────────────

def load_log(
    path: str | Path,
    tz_aware: bool = False,
) -> tuple[pd.DataFrame, AirframeInfo]:
    """
    Load a single G3X EIS log file.

    Supports both export paths transparently:
      • g3x_direct   — CSV downloaded directly from the G3X SD card
      • garmin_pilot — CSV exported/shared through the Garmin Pilot app
                       (header row prefixed with '#')

    The detected format is recorded on `info.source_format` so you can
    confirm which path produced a given file, but no other behaviour
    differs between the two — both normalise to identical columns.

    Returns
    -------
    df : pd.DataFrame
        1-row-per-second data, typed and normalised.
        Includes derived columns: `datetime`, `elapsed_s`,
        `egt_spread_f`, `egt_max_f`, `egt_min_f`, `egt_mean_f`,
        `fuel_flow_lph` (litres/hour for OM limit comparisons).
    info : AirframeInfo
        Parsed metadata from the file header, including `source_format`.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log not found: {path}")

    # Read metadata row 0 and header row 1 (need both before pandas parses the body)
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        meta_row   = f.readline()
        header_row = f.readline()

    info = AirframeInfo.from_row(meta_row)
    info.source_format = _detect_source_format(header_row)

    if info.source_format == "unknown":
        raise ValueError(
            f"{path.name}: unrecognised header format — expected a G3X-direct "
            f"download ('Date (yyyy-mm-dd)...') or a Garmin Pilot export "
            f"('#Date (yyyy-mm-dd)...'). Got: {header_row[:60]!r}. "
            f"This file may be corrupted or from an unsupported source."
        )

    # Read data (skip metadata row, row 1 is headers)
    df = pd.read_csv(path, skiprows=1, low_memory=False, encoding="utf-8-sig")

    # Garmin Pilot exports prefix the header row with '#' (e.g. "#Date (yyyy-mm-dd)")
    # while direct G3X SD-card downloads do not. Strip it — along with any stray
    # whitespace from spreadsheet round-trips — so both formats normalise to the
    # same column names regardless of source_format.
    df.columns = [str(c).lstrip("#").strip() for c in df.columns]

    # Drop the sub-header row if present (some firmware versions insert one)
    first_col = df.columns[0]
    mask = df[first_col].astype(str).str.contains("Lcl Date|Date", na=False)
    df = df[~mask].reset_index(drop=True)

    # Rename columns
    df = df.rename(columns=COLUMN_MAP)

    # Drop columns not in our map (keep them for completeness but don't rename)
    # (Any unmapped columns stay with their original name)

    # ── Datetime ──────────────────────────────────────────────────────────────
    df["datetime"] = pd.to_datetime(
        df["date"].astype(str) + " " + df["time"].astype(str),
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce"
    )
    df = df.dropna(subset=["datetime"]).reset_index(drop=True)
    df["elapsed_s"] = (df["datetime"] - df["datetime"].iloc[0]).dt.total_seconds()

    # ── Numeric conversion ────────────────────────────────────────────────────
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Derived columns ───────────────────────────────────────────────────────
    # EGT analytics
    egt_avail = [c for c in EGT_COLS if c in df.columns]
    if egt_avail:
        df["egt_max_f"]    = df[egt_avail].max(axis=1)
        df["egt_min_f"]    = df[egt_avail].min(axis=1)
        df["egt_mean_f"]   = df[egt_avail].mean(axis=1)
        df["egt_spread_f"] = df["egt_max_f"] - df["egt_min_f"]

    # Fuel flow in litres/hour (for OM EGT-split limit which uses L/hr)
    if "fuel_flow_gph" in df.columns:
        df["fuel_flow_lph"] = df["fuel_flow_gph"] * 3.78541

    # OAT in Fahrenheit
    if "oat_c" in df.columns:
        df["oat_f"] = df["oat_c"] * 9/5 + 32

    # MAP in hPa (for OM limit comparisons which use hPa)
    if "map_inhg" in df.columns:
        df["map_hpa"] = df["map_inhg"] * 33.8639

    # Oil temp in Celsius
    if "oil_temp_f" in df.columns:
        df["oil_temp_c"] = (df["oil_temp_f"] - 32) * 5/9

    # Coolant temp in Celsius
    if "coolant_temp_f" in df.columns:
        df["coolant_temp_c"] = (df["coolant_temp_f"] - 32) * 5/9

    # EGT in Celsius
    for col in egt_avail:
        df[col.replace("_f", "_c")] = (df[col] - 32) * 5/9

    # Source file metadata
    df["_source_file"] = path.name

    return df, info


def load_directory(
    directory: str | Path,
    pattern: str = "*.csv",
    skip_ground_sessions: bool = True,
    min_airborne_min: float = 3.0,
    verbose: bool = True,
) -> list[tuple[pd.DataFrame, AirframeInfo]]:
    """
    Load all G3X log files from a directory.

    Matches the given pattern case-insensitively (so '*.csv' also picks up
    '.CSV', '.Csv', etc. — Garmin Pilot and some OS file pickers vary in
    the case they save with). Files are de-duplicated by resolved path so
    a case-insensitive match never double-counts the same file.

    Parameters
    ----------
    skip_ground_sessions : bool, default True
        Exclude ground-only sessions (engine run-up, taxi test, avionics
        check) where the aircraft never actually flew. These sessions have
        near-zero airborne time and no useful flight analytics — including
        them produces misleading results in every downstream module
        (false temperature outliers, meaningless phase labels, blank cells
        across most analytics columns). They also inflate counts and degrade
        trend quality by adding x-axis points with identical engine-hours.

        Ground-session detection: a file is excluded if its estimated
        airborne time (rows with RPM > 3,000 AND IAS > 30kt) is less than
        min_airborne_min. This is an approximation that doesn't require
        running the full phase-detection state machine at load time.

        Pass skip_ground_sessions=False only if you specifically need to
        examine ground sessions (e.g. for ENGINE ECU powerup behavior
        in isolation from flight operations — but note that full flights
        contain all the same POWERUP/LANE_CHECK/SHUTDOWN patterns and are
        sufficient to establish those baselines without the noise).

    min_airborne_min : float, default 3.0
        Threshold in minutes for the ground-session filter. Files with
        estimated airborne time below this are excluded when
        skip_ground_sessions=True.

    Returns a list of (DataFrame, AirframeInfo) tuples,
    sorted chronologically by the datetime of the first record.
    """
    directory = Path(directory)

    # Case-insensitive glob: build a regex from the pattern and scan once,
    # rather than relying on Path.glob (which is case-sensitive on
    # Linux/Mac and would silently skip e.g. '.CSV' files).
    import re as _re
    regex = _re.compile(
        "^" + _re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$",
        _re.IGNORECASE,
    )
    seen: set[Path] = set()
    files = []
    for f in directory.iterdir():
        if f.is_file() and regex.match(f.name):
            resolved = f.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(f)
    files.sort()

    if not files:
        raise ValueError(f"No files matching '{pattern}' (case-insensitive) in {directory}")

    if verbose:
        print(f"Found {len(files)} file(s) matching '{pattern}' in {directory}")

    results = []
    failed  = []
    skipped = []

    for f in files:
        try:
            df, info = load_log(f)

            # ── Ground-session detection ───────────────────────────────────
            # Estimate airborne time without running the full phase-detection
            # state machine: count rows where the engine is running AND the
            # aircraft is moving at flight speed. This is fast (no VS/altitude
            # smoothing needed) and sufficient for a binary ground/flight split.
            if skip_ground_sessions:
                ias = df["ias_kt"].fillna(0) if "ias_kt" in df.columns else pd.Series(0, index=df.index)
                rpm = df["rpm"].fillna(0)    if "rpm"    in df.columns else pd.Series(0, index=df.index)
                airborne_rows = ((rpm > 3000) & (ias > 30)).sum()
                airborne_min  = airborne_rows / 60.0   # 1Hz logging → rows ≈ seconds
                if airborne_min < min_airborne_min:
                    skipped.append(f.name)
                    if verbose:
                        print(f"  · {f.name}  [{df['datetime'].iloc[0]:%Y-%m-%d %H:%M}]  "
                              f"ground session ({airborne_min:.1f} min airborne) — skipped")
                    continue

            results.append((df, info))
            if verbose:
                start = df["datetime"].iloc[0]
                end   = df["datetime"].iloc[-1]
                dur   = (end - start).total_seconds() / 60
                fmt   = {"g3x_direct": "G3X", "garmin_pilot": "GarminPilot"}.get(
                    info.source_format, info.source_format)
                print(f"  ✓ {f.name}  [{start:%Y-%m-%d %H:%M}]  {dur:.0f} min  "
                      f"{len(df)} rows  {info.aircraft_ident}  ({fmt})")
        except Exception as e:
            failed.append((f.name, str(e)))
            if verbose:
                print(f"  ✗ {f.name}: {e}")

    # Sort by first timestamp
    results.sort(key=lambda r: r[0]["datetime"].iloc[0])
    if verbose:
        print(f"\nLoaded {len(results)} flight(s)"
              + (f", skipped {len(skipped)} ground session(s)" if skipped else "")
              + (f", {len(failed)} failed" if failed else "")
              + f"  (total files found: {len(files)})")
        if failed:
            print(f"⚠ Failed files:")
            for name, err in failed:
                print(f"    {name}: {err}")
    return results
    return results


# ── Quick summary ─────────────────────────────────────────────────────────────

def log_summary(df: pd.DataFrame, info: AirframeInfo) -> dict:
    """Return a flat summary dict for a single flight."""
    start = df["datetime"].iloc[0]
    end   = df["datetime"].iloc[-1]
    dur_s = (end - start).total_seconds()

    airborne = df[df["rpm"].fillna(0) > 3000]

    summary = {
        "aircraft":      info.aircraft_ident,
        "date":          start.date(),
        "local_start":   start,
        "local_end":     end,
        "duration_min":  dur_s / 60,
        "rows":          len(df),
        "interval_s":    df["elapsed_s"].diff().mode()[0] if len(df) > 1 else None,
        "airborne_rows": len(airborne),
        "airborne_min":  len(airborne) / 60,
        "engine_hours_at_log": info.engine_hours,
        "source_file":   df["_source_file"].iloc[0],
        "source_format": info.source_format,
    }

    # Engine peaks (airborne)
    for col, label in [
        ("rpm",          "max_rpm"),
        ("power_pct",    "max_power_pct"),
        ("egt_max_f",    "max_egt_f"),
        ("egt_spread_f", "max_egt_spread_f"),
        ("oil_temp_f",   "max_oil_temp_f"),
        ("coolant_temp_f", "max_coolant_temp_f"),
        ("map_inhg",     "max_map_inhg"),
        ("fuel_flow_gph","max_fuel_flow_gph"),
    ]:
        if col in airborne.columns:
            summary[label] = airborne[col].dropna().max() if len(airborne) else None

    # Mean fuel flow in cruise (rough: airborne, VS settled)
    cruise = airborne[
        (airborne["vs_fpm"].abs() < 300) &
        (airborne["ias_kt"] > 60)
    ] if "vs_fpm" in airborne.columns and "ias_kt" in airborne.columns else pd.DataFrame()
    summary["cruise_fuel_flow_gph"] = cruise["fuel_flow_gph"].mean() if len(cruise) else None

    return summary


# ── Duplicate flight detection ─────────────────────────────────────────────────

@dataclass
class DuplicateGroup:
    """A set of files judged to represent the same physical flight."""
    files: list[str]
    aircraft_ident: str
    overlap_start: pd.Timestamp
    overlap_end: pd.Timestamp
    match_kind: str    # "exact" | "overlap"
    detail: str

    def __str__(self):
        names = ", ".join(self.files)
        return (f"[{self.match_kind}] {self.aircraft_ident}  "
                f"{self.overlap_start:%Y-%m-%d %H:%M}–{self.overlap_end:%H:%M}  "
                f"({names})  — {self.detail}")


def flight_fingerprint(df: pd.DataFrame, info: AirframeInfo) -> tuple:
    """
    A coarse identity key for a flight: same aircraft, same G3X unit,
    same start minute. Two files sharing this fingerprint are almost
    certainly the same physical flight exported through different paths
    (e.g. SD-card download vs. Garmin Pilot export) — start time alone
    can't distinguish them since both preserve the original timestamps.

    Truncated to the minute (not the second) deliberately: some export
    paths round or drop the first partial second, so an exact-second
    match is too strict and would miss genuine duplicates.
    """
    start_minute = df["datetime"].iloc[0].floor("min") if len(df) else None
    return (info.aircraft_ident, info.system_id, start_minute)


def find_duplicate_flights(
    flights: list[tuple[pd.DataFrame, AirframeInfo]],
    overlap_threshold: float = 0.8,
) -> list[DuplicateGroup]:
    """
    Detect flights in a loaded batch that represent the same physical
    flight, via two passes:

    1. EXACT — same aircraft + same G3X unit + same start minute.
       This catches the common case: the same flight exported once
       directly from the SD card and once via Garmin Pilot.

    2. OVERLAP — same aircraft + time windows overlap by more than
       `overlap_threshold` of the shorter flight's duration, even if
       start times differ (e.g. one export is missing the first few
       minutes of avionics-on time that the other captured).

    Returns a list of DuplicateGroup objects. An empty list means no
    duplicates were found. This does NOT decide which file to keep —
    that's a judgement call (e.g. prefer the higher row-count / more
    complete export), left to the caller.
    """
    groups: list[DuplicateGroup] = []
    seen_pairs: set[frozenset] = set()

    # ── Pass 1: exact fingerprint match ──────────────────────────────────────
    by_fingerprint: dict[tuple, list[int]] = {}
    for idx, (df, info) in enumerate(flights):
        fp = flight_fingerprint(df, info)
        by_fingerprint.setdefault(fp, []).append(idx)

    for fp, idxs in by_fingerprint.items():
        if len(idxs) > 1:
            names = [flights[i][0]["_source_file"].iloc[0] for i in idxs]
            starts = [flights[i][0]["datetime"].iloc[0] for i in idxs]
            ends   = [flights[i][0]["datetime"].iloc[-1] for i in idxs]
            row_counts = [len(flights[i][0]) for i in idxs]
            groups.append(DuplicateGroup(
                files=names,
                aircraft_ident=fp[0],
                overlap_start=min(starts),
                overlap_end=max(ends),
                match_kind="exact",
                detail=f"identical start minute; row counts: {row_counts}",
            ))
            seen_pairs.add(frozenset(idxs))

    # ── Pass 2: time-window overlap (catches near-matches the exact pass missed) ──
    n = len(flights)
    for i in range(n):
        for j in range(i + 1, n):
            key = frozenset([i, j])
            if key in seen_pairs:
                continue   # already caught by exact match

            df_a, info_a = flights[i]
            df_b, info_b = flights[j]
            if info_a.aircraft_ident != info_b.aircraft_ident:
                continue
            if not info_a.aircraft_ident:
                continue   # can't compare unknown aircraft

            a_start, a_end = df_a["datetime"].iloc[0], df_a["datetime"].iloc[-1]
            b_start, b_end = df_b["datetime"].iloc[0], df_b["datetime"].iloc[-1]

            overlap_start = max(a_start, b_start)
            overlap_end   = min(a_end, b_end)
            overlap_s = (overlap_end - overlap_start).total_seconds()
            if overlap_s <= 0:
                continue   # no time overlap at all

            a_dur = (a_end - a_start).total_seconds()
            b_dur = (b_end - b_start).total_seconds()
            shorter_dur = min(a_dur, b_dur)
            if shorter_dur <= 0:
                continue

            overlap_frac = overlap_s / shorter_dur
            if overlap_frac >= overlap_threshold:
                groups.append(DuplicateGroup(
                    files=[df_a["_source_file"].iloc[0], df_b["_source_file"].iloc[0]],
                    aircraft_ident=info_a.aircraft_ident,
                    overlap_start=overlap_start,
                    overlap_end=overlap_end,
                    match_kind="overlap",
                    detail=f"{overlap_frac*100:.0f}% time overlap "
                           f"(rows: {len(df_a)} vs {len(df_b)})",
                ))

    return groups


def deduplicate_flights(
    flights: list[tuple[pd.DataFrame, AirframeInfo]],
    prefer: str = "most_rows",
    verbose: bool = True,
) -> list[tuple[pd.DataFrame, AirframeInfo]]:
    """
    Remove duplicate flights from a loaded batch, keeping one
    representative per duplicate group.

    prefer:
        "most_rows" (default) — keep the file with more data rows,
            on the theory that a more complete capture (e.g. SD-card
            download that wasn't truncated) is the better source.
        "g3x_direct" — prefer a G3X-direct download over a Garmin
            Pilot export when both are present in the group.

    This is a convenience wrapper around find_duplicate_flights() for
    callers (like 03_multi_flight_insights.py) that just want a clean
    deduplicated list without examining the groups themselves.
    """
    dup_groups = find_duplicate_flights(flights)
    if not dup_groups:
        return flights

    # Map source_file -> index for quick lookup
    file_to_idx = {df["_source_file"].iloc[0]: i for i, (df, _) in enumerate(flights)}

    drop_indices: set[int] = set()
    for group in dup_groups:
        idxs = [file_to_idx[f] for f in group.files if f in file_to_idx]
        if len(idxs) < 2:
            continue

        if prefer == "g3x_direct":
            g3x_idxs = [i for i in idxs if flights[i][1].source_format == "g3x_direct"]
            keep = g3x_idxs[0] if g3x_idxs else max(idxs, key=lambda i: len(flights[i][0]))
        else:  # most_rows
            keep = max(idxs, key=lambda i: len(flights[i][0]))

        for i in idxs:
            if i != keep:
                drop_indices.add(i)

        if verbose:
            kept_name = flights[keep][0]["_source_file"].iloc[0]
            dropped_names = [flights[i][0]["_source_file"].iloc[0] for i in idxs if i != keep]
            print(f"  ⚠ Duplicate flight detected ({group.match_kind}): "
                  f"keeping '{kept_name}', dropping {dropped_names}")

    return [f for i, f in enumerate(flights) if i not in drop_indices]
