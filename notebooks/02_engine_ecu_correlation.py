"""
notebooks/02_engine_ecu_correlation.py
=======================================
Multi-flight ENGINE ECU correlation analysis.

Goals
-----
1. Classify every ENGINE ECU run across all flights into one of four categories:

   POWERUP    — before engine start; expected, suppress in UI
   SHUTDOWN   — after engine stops; expected, suppress in UI
   LANE_CHECK — deliberate single-lane run-up test (Lane A off → on,
                Lane B off → on); expected pre-takeoff procedure,
                suppress in UI but log for completeness
   IN_FLIGHT  — engine running, not a lane check; the real signal

   LANE_CHECK detection signature:
     • RPM in run-up band (3,000–5,000 rpm)
     • IAS near zero (on ground, <20 kt)
     • Duration short (≤15 seconds)
     • Occurs in pairs within 60 seconds (one per lane)

2. For IN_FLIGHT runs, find correlated parameter signatures.

3. Determine whether the pattern is consistent across flights.

Run from any directory (PyCharm, terminal, Jupyter):
    python notebooks/02_engine_ecu_correlation.py

Output
------
  Console: per-flight summary + aggregate statistics
  File:    data/reports/engine_ecu_report.txt
  File:    data/reports/engine_ecu_runs.csv
"""

import sys
from pathlib import Path

_HERE    = Path(__file__).resolve().parent
_TOOLKIT = _HERE.parent
sys.path.insert(0, str(_TOOLKIT))

from slingology_eis.loader import load_directory, find_duplicate_flights, deduplicate_flights
from slingology_eis.cas import _split_cas
from slingology_eis.limits import load_engine_config

import pandas as pd
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
LOGS_DIR    = _TOOLKIT / "data" / "logs"
REPORTS_DIR = _TOOLKIT / "data" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Load engine config (reads from config.json or defaults to 916iS)
_engine_cfg = load_engine_config()
_phase_cfg  = _engine_cfg.get("phase_detection", {})

RPM_RUNNING               = 500
VOLTAGE_DECLINE_THRESHOLD = 0.5   # V drop over run → SHUTDOWN

# Lane check detection thresholds — from engine config
LANE_CHECK_MAX_DURATION_S = _phase_cfg.get("lane_check_max_duration_s", 15)
LANE_CHECK_RPM_MIN        = _phase_cfg.get("runup_rpm_min", 3000)
LANE_CHECK_RPM_MAX        = _phase_cfg.get("runup_rpm_max", 5000)
LANE_CHECK_MAX_IAS_KT     = 20    # ground-speed criterion — not engine-specific
LANE_CHECK_PAIR_WINDOW_S  = 90    # both lanes tested within this window

CONTEXT_WINDOW = 5

CORR_PARAMS = [
    "rpm", "power_pct", "map_inhg", "map_hpa",
    "oil_press_psi", "oil_temp_f", "coolant_temp_f",
    "fuel_flow_gph", "fuel_press_psi",
    "egt1_f", "egt2_f", "egt3_f", "egt4_f", "egt_spread_f",
    "main_volts", "batt_amps", "efis_bkup_v", "nav_bkup_v",
    "ias_kt", "baro_alt_ft", "vs_fpm",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def ecu_active_series(df: pd.DataFrame) -> pd.Series:
    return df["cas_alert"].apply(lambda v: "ENGINE ECU" in _split_cas(v))


def classify_run(df: pd.DataFrame, start_idx: int, end_idx: int) -> str:
    """
    Classify an ENGINE ECU run into one of four categories:
    POWERUP | SHUTDOWN | LANE_CHECK | IN_FLIGHT
    """
    seg        = df.loc[start_idx:end_idx]
    rpm_vals   = seg["rpm"].fillna(0)
    engine_rows = (rpm_vals > RPM_RUNNING).sum()
    total_rows  = len(seg)
    dur_s       = total_rows  # 1-second logging

    # ── POWERUP / SHUTDOWN ────────────────────────────────────────────────────
    if engine_rows / total_rows < 0.3:
        if "main_volts" in seg.columns:
            volts = seg["main_volts"].dropna()
            if len(volts) >= 3:
                if volts.iloc[:3].mean() > volts.iloc[-3:].mean() + VOLTAGE_DECLINE_THRESHOLD:
                    return "SHUTDOWN"
        return "POWERUP"

    # ── LANE_CHECK ────────────────────────────────────────────────────────────
    # Must be: short, in run-up RPM band, nearly stationary
    mean_rpm = float(rpm_vals[rpm_vals > RPM_RUNNING].mean()) if engine_rows else 0
    mean_ias = float(seg["ias_kt"].fillna(0).mean()) if "ias_kt" in seg.columns else 99

    if (dur_s <= LANE_CHECK_MAX_DURATION_S
            and LANE_CHECK_RPM_MIN <= mean_rpm <= LANE_CHECK_RPM_MAX
            and mean_ias <= LANE_CHECK_MAX_IAS_KT):
        return "LANE_CHECK"

    return "IN_FLIGHT"


def extract_runs(df: pd.DataFrame) -> list[dict]:
    """Extract all ENGINE ECU runs with classification and statistics."""
    ecu = ecu_active_series(df)
    raw_runs = []
    in_run, start = False, None

    for i in df.index:
        if ecu.loc[i] and not in_run:
            in_run, start = True, i
        elif not ecu.loc[i] and in_run:
            in_run = False
            raw_runs.append((start, i - 1))
    if in_run and start is not None:
        raw_runs.append((start, df.index[-1]))

    # Build run dicts
    runs = [_build_run(df, s, e) for s, e in raw_runs]

    # ── Pair lane checks: if two LANE_CHECK runs are within the pair window,
    #    annotate each with its pair partner ────────────────────────────────
    lane_checks = [(i, r) for i, r in enumerate(runs) if r["classification"] == "LANE_CHECK"]
    for j in range(len(lane_checks) - 1):
        idx_a, r_a = lane_checks[j]
        idx_b, r_b = lane_checks[j + 1]
        gap_s = (r_b["start_time"] - r_a["end_time"]).total_seconds()
        if gap_s <= LANE_CHECK_PAIR_WINDOW_S:
            runs[idx_a]["lane_check_pair"] = True
            runs[idx_b]["lane_check_pair"] = True
            runs[idx_a]["lane_check_note"] = f"Lane A test (paired with run at {r_b['start_time']:%H:%M:%S})"
            runs[idx_b]["lane_check_note"] = f"Lane B test (paired with run at {r_a['start_time']:%H:%M:%S})"

    return runs


def _build_run(df: pd.DataFrame, start_idx: int, end_idx: int) -> dict:
    seg     = df.loc[start_idx:end_idx]
    t_start = seg["datetime"].iloc[0]
    t_end   = seg["datetime"].iloc[-1]
    dur_s   = (t_end - t_start).total_seconds() + 1
    kind    = classify_run(df, start_idx, end_idx)

    pre_start = max(df.index[0], start_idx - CONTEXT_WINDOW)
    pre       = df.loc[pre_start: start_idx - 1]

    oil_nan_frac = seg["oil_press_psi"].isna().mean() if "oil_press_psi" in seg.columns else None

    rpm_accel_pre = None
    if "rpm" in pre.columns and len(pre) >= 2:
        rpm_vals = pre["rpm"].dropna()
        if len(rpm_vals) >= 2:
            rpm_accel_pre = float(rpm_vals.diff().mean())

    volts_at_start, volts_delta = None, None
    if "main_volts" in df.columns:
        v_now = seg["main_volts"].dropna()
        v_pre = pre["main_volts"].dropna()
        if len(v_now):
            volts_at_start = float(v_now.iloc[0])
        if len(v_now) and len(v_pre):
            volts_delta = float(v_now.iloc[0]) - float(v_pre.iloc[-1])

    co_alerts: set[str] = set()
    for v in seg["cas_alert"].dropna():
        for a in _split_cas(v):
            if a != "ENGINE ECU":
                co_alerts.add(a)

    param_means = {}
    for col in ["rpm", "power_pct", "oil_press_psi", "oil_temp_f",
                "coolant_temp_f", "main_volts", "batt_amps",
                "fuel_press_psi", "ias_kt", "baro_alt_ft"]:
        if col in seg.columns:
            v = seg[col].dropna()
            param_means[col] = round(float(v.mean()), 2) if len(v) else None

    return {
        "source_file":      df["_source_file"].iloc[0],
        "date":             t_start.date(),
        "start_time":       t_start,
        "end_time":         t_end,
        "duration_s":       dur_s,
        "classification":   kind,
        "lane_check_pair":  False,
        "lane_check_note":  "",
        "start_idx":        start_idx,
        "end_idx":          end_idx,
        "oil_nan_frac":     oil_nan_frac,
        "rpm_accel_pre":    rpm_accel_pre,
        "volts_at_start":   volts_at_start,
        "volts_delta":      volts_delta,
        "co_alerts":        sorted(co_alerts),
        **{f"mean_{k}": v for k, v in param_means.items()},
    }


def correlation_analysis(df: pd.DataFrame) -> pd.Series:
    running = df[df["rpm"].fillna(0) > RPM_RUNNING].copy()
    if len(running) < 10:
        return pd.Series(dtype=float)
    running["ecu_active"] = ecu_active_series(running).astype(float)
    available = [c for c in CORR_PARAMS if c in running.columns]
    corr = running[available + ["ecu_active"]].corr()["ecu_active"].drop("ecu_active")
    return corr.sort_values(key=abs, ascending=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  SLINGOLOGY EIS — ENGINE ECU Multi-Flight Correlation Analysis")
    print("=" * 70)

    print(f"\nLoading logs from: {LOGS_DIR}")
    try:
        flights = load_directory(str(LOGS_DIR), verbose=True)
    except ValueError as e:
        print(f"\nError: {e}")
        print("Place G3X CSV log files in the data/logs/ directory and re-run.")
        return

    dup_groups = find_duplicate_flights(flights)
    if dup_groups:
        print(f"\n⚠  {len(dup_groups)} duplicate flight group(s) detected:")
        for g in dup_groups:
            print(f"    {g}")
        flights = deduplicate_flights(flights, prefer="most_rows", verbose=True)
        print(f"  Proceeding with {len(flights)} unique flight(s).")

    all_runs: list[dict]  = []
    flight_summaries      = []

    # ── Per-flight ────────────────────────────────────────────────────────────
    for df, info in flights:
        fname = df["_source_file"].iloc[0]
        date  = df["datetime"].iloc[0].date()
        total = len(df)
        ecu   = ecu_active_series(df)
        n_ecu = ecu.sum()
        runs  = extract_runs(df)

        n_powerup    = sum(1 for r in runs if r["classification"] == "POWERUP")
        n_shutdown   = sum(1 for r in runs if r["classification"] == "SHUTDOWN")
        n_lanecheck  = sum(1 for r in runs if r["classification"] == "LANE_CHECK")
        n_inflight   = sum(1 for r in runs if r["classification"] == "IN_FLIGHT")
        s_inflight   = sum(r["duration_s"] for r in runs if r["classification"] == "IN_FLIGHT")
        paired_lc    = sum(1 for r in runs if r.get("lane_check_pair"))

        all_runs.extend(runs)
        flight_summaries.append({
            "file": fname, "date": date, "total_rows": total,
            "ecu_rows": int(n_ecu), "ecu_pct": round(n_ecu / total * 100, 1),
            "runs_powerup": n_powerup, "runs_shutdown": n_shutdown,
            "runs_lanecheck": n_lanecheck, "runs_inflight": n_inflight,
            "inflight_ecu_s": s_inflight, "aircraft": info.aircraft_ident,
            "engine_hours": info.engine_hours,
        })

        flag = "⚡" if n_inflight > 0 else "✓"
        print(f"\n  {flag} {fname}")
        print(f"     Date: {date}  |  Aircraft: {info.aircraft_ident}  "
              f"|  Engine hrs: {info.engine_hours}")
        print(f"     ENGINE ECU: {n_ecu} rows ({n_ecu/total*100:.1f}%)  —  "
              f"{n_powerup} powerup  "
              f"{n_lanecheck} lane-check ({paired_lc} paired)  "
              f"{n_shutdown} shutdown  "
              f"{n_inflight} IN-FLIGHT")

        for r in runs:
            c = r["classification"]
            symbol = {"POWERUP": "·", "SHUTDOWN": "·",
                      "LANE_CHECK": "✓", "IN_FLIGHT": "⚡"}.get(c, "?")
            note = r.get("lane_check_note") or ""
            oil  = (f"  oil_NaN:{r['oil_nan_frac']*100:.0f}%"
                    if r["oil_nan_frac"] is not None and c != "POWERUP" else "")
            print(f"       {symbol} [{c:<11}] {r['start_time']:%H:%M:%S}  "
                  f"{r['duration_s']:.0f}s{oil}  {note}")

    # ── Aggregate ─────────────────────────────────────────────────────────────
    runs_df     = pd.DataFrame(all_runs)
    inflight_df = runs_df[runs_df["classification"] == "IN_FLIGHT"].copy()
    lanecheck_df = runs_df[runs_df["classification"] == "LANE_CHECK"].copy()

    print(f"\n{'=' * 70}")
    print("  AGGREGATE SUMMARY")
    print("=" * 70)
    print(f"\n  Flights analysed:        {len(flights)}")
    print(f"  Total ENGINE ECU runs:   {len(runs_df)}")
    print(f"    POWERUP   (expected):  {(runs_df['classification']=='POWERUP').sum()}")
    print(f"    LANE_CHECK (expected): {(runs_df['classification']=='LANE_CHECK').sum()}  "
          f"({lanecheck_df['lane_check_pair'].sum()} paired)")
    print(f"    SHUTDOWN  (expected):  {(runs_df['classification']=='SHUTDOWN').sum()}")
    print(f"    IN_FLIGHT (signal):    {(runs_df['classification']=='IN_FLIGHT').sum()}")

    # Lane check consistency
    if len(lanecheck_df) > 0:
        print(f"\n  Lane check analysis:")
        paired = lanecheck_df["lane_check_pair"].sum()
        print(f"    Paired runs (both lanes tested): {paired}/{len(lanecheck_df)}")
        lc_dur = lanecheck_df["duration_s"]
        print(f"    Duration: mean={lc_dur.mean():.1f}s  "
              f"min={lc_dur.min():.0f}s  max={lc_dur.max():.0f}s")
        lc_oil = lanecheck_df["oil_nan_frac"].dropna()
        if len(lc_oil):
            print(f"    Oil press NaN during lane off: mean={lc_oil.mean()*100:.0f}%")
            print(f"    → Oil NaN during lane test is EXPECTED (FADEC CAN pauses briefly)")

    # In-flight anomalies
    if len(inflight_df) > 0:
        print(f"\n  ⚡ IN-FLIGHT runs:")
        print(f"    Flights affected: {inflight_df['source_file'].nunique()}/{len(flights)}")
        print(f"    Total duration:   {inflight_df['duration_s'].sum():.0f}s")
        _print_inflight_detail(inflight_df)
    else:
        print(f"\n  ✓ No IN-FLIGHT ENGINE ECU runs detected.")
        print(f"    All occurrences are normal: powerup, lane checks, shutdown.")

    # ── Grand correlation ──────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  PARAMETER CORRELATION WITH ENGINE ECU (engine-running rows only)")
    print("=" * 70)

    all_running = []
    for df, _ in flights:
        running = df[df["rpm"].fillna(0) > RPM_RUNNING].copy()
        if len(running) >= 10:
            running["ecu_active"] = ecu_active_series(running).astype(float)
            all_running.append(running)

    if all_running:
        combined  = pd.concat(all_running, ignore_index=True)
        available = [c for c in CORR_PARAMS if c in combined.columns]
        grand_corr = (combined[available + ["ecu_active"]]
                      .corr()["ecu_active"]
                      .drop("ecu_active")
                      .sort_values(key=abs, ascending=False))

        print(f"\n  Grand correlation (N={len(combined):,} engine-running rows):\n")
        for param, r in grand_corr.items():
            if abs(r) < 0.01:
                continue
            bar   = "▓" * int(abs(r) * 40)
            sign  = "+" if r >= 0 else "-"
            stars = (" ★★★" if abs(r) > 0.3 else
                     " ★★"  if abs(r) > 0.15 else
                     " ★"   if abs(r) > 0.08 else "")
            print(f"  {param:<22} r={sign}{abs(r):.4f}  {bar}{stars}")

    # ── Per-flight trend ───────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  PER-FLIGHT IN-FLIGHT RUN COUNT (chronological)")
    print("=" * 70)
    for s in flight_summaries:
        bar = "█" * s["runs_inflight"] if s["runs_inflight"] > 0 else "—"
        hrs = f"  {s['engine_hours']}h" if s["engine_hours"] else ""
        lc  = f"  lc:{s['runs_lanecheck']}"
        print(f"  {s['date']}  {s['runs_inflight']:2d} in-flight  {bar:<10}"
              f"{lc}{hrs}  {s['file']}")

    # ── Save ──────────────────────────────────────────────────────────────────
    out_csv = REPORTS_DIR / "engine_ecu_runs.csv"
    runs_df.to_csv(out_csv, index=False)

    out_txt = REPORTS_DIR / "engine_ecu_report.txt"
    _write_text_report(flights, runs_df, flight_summaries, out_txt)

    print(f"\n  Saved: {out_csv}")
    print(f"  Saved: {out_txt}")
    print(f"\n{'=' * 70}\n")


def _inflight_detail_lines(inflight_df: pd.DataFrame) -> list[str]:
    """
    Build the IN-FLIGHT interpretation/recommendation lines once, so both
    the console output and the saved text report show the same analysis —
    previously this only existed in the console, leaving the saved
    engine_ecu_report.txt without the actual interpretation.
    """
    lines = []
    oil_nan_consistent = (
        (inflight_df["oil_nan_frac"] > 0.8).mean() > 0.6
        if "oil_nan_frac" in inflight_df.columns else False
    )
    if oil_nan_consistent:
        lines.append("    Oil press NaN co-occurrence: STRONG → CAN bus dropout pattern")
    else:
        lines.append("    Oil press NaN co-occurrence: mixed — investigate further")

    co_counter: dict[str, int] = {}
    for _, row in inflight_df.iterrows():
        for a in row.get("co_alerts", []):
            co_counter[a] = co_counter.get(a, 0) + 1
    if co_counter:
        lines.append(f"    Co-active alerts: {co_counter}")
    else:
        lines.append("    No co-active alerts — ENGINE ECU isolated → CAN fault, not ECU hardware")

    lines.append("")
    lines.append("    RECOMMENDED ACTIONS:")
    lines.append("    1. Inspect Rotax Display CAN at GEA-24 (J244 pins 17 & 33)")
    lines.append("    2. Inspect & reseat HIC A and HIC B connector bodies")
    lines.append("    3. Pull B.U.D.S. fault log — both Lane A and Lane B")
    return lines


def _print_inflight_detail(inflight_df: pd.DataFrame):
    for line in _inflight_detail_lines(inflight_df):
        print(line)


def _write_text_report(flights, runs_df, summaries, out_path: Path):
    lines = [
        "SLINGOLOGY EIS — ENGINE ECU CORRELATION REPORT",
        f"Flights: {len(flights)}",
        "=" * 70, "",
    ]
    for s in summaries:
        lines += [
            f"Flight: {s['file']}",
            f"  {s['date']}  {s['aircraft']}  {s['engine_hours']}h",
            f"  POWERUP:{s['runs_powerup']}  LANE_CHECK:{s['runs_lanecheck']}  "
            f"SHUTDOWN:{s['runs_shutdown']}  IN-FLIGHT:{s['runs_inflight']}", "",
        ]

    # ── IN-FLIGHT interpretation — previously console-only, now in the
    #    saved report too, so the actual analysis survives past the
    #    terminal session that produced it. ─────────────────────────────────
    inflight_df = runs_df[runs_df["classification"] == "IN_FLIGHT"] if len(runs_df) else runs_df
    lines += ["", "IN-FLIGHT ENGINE ECU INTERPRETATION:", "-" * 70]
    if len(inflight_df) > 0:
        lines.append(f"  {len(inflight_df)} IN-FLIGHT occurrence(s) across "
                     f"{inflight_df['source_file'].nunique()} flight(s):")
        lines += _inflight_detail_lines(inflight_df)
    else:
        lines.append("  No IN-FLIGHT ENGINE ECU occurrences detected — all occurrences")
        lines.append("  classified as expected (POWERUP / LANE_CHECK / SHUTDOWN).")
    lines.append("")

    lines += ["ALL RUNS:", "-" * 70]
    for _, row in runs_df.iterrows():
        lines.append(
            f"  [{row['classification']:<11}] {row['source_file']}  "
            f"{row['start_time']:%Y-%m-%d %H:%M:%S}  {row['duration_s']:.0f}s  "
            f"oil_nan:{(row.get('oil_nan_frac') or 0):.0%}  "
            f"note:{row.get('lane_check_note','')}  co:{row.get('co_alerts',[])}"
        )
    out_path.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
