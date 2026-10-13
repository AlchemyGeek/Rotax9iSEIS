"""
notebooks/02_engine_ecu_correlation.py
=======================================
Multi-flight ENGINE ECU correlation analysis.

Research tool only — not reachable from the CLI or the per-flight report.
The engine's own ENGINE ECU result is `analyze_ecu` (Spec 01 §8.6).

Goals
-----
1. List every ENGINE ECU run across all flights with its classification by
   flight phase (Spec 01 §8.6, v0.19):

   GROUND_START    — PRE_START / ENGINE_START / WARMUP; expected
   LANE_CHECK      — deliberate single-lane run-up in WARMUP/TAXI (run-up
                     RPM band, stationary, short, paired one per lane);
                     expected
   GROUND          — engine running on the ground, not a lane check
   IN_FLIGHT       — TAKEOFF_ROLL through LANDING_ROLL; the only flight event
   GROUND_SHUTDOWN — SHUTDOWN; expected

   Runs shorter than the profile's cas.min_event_duration_s are counted as
   sub-threshold blips, not runs.

2. Correlate ENGINE ECU activity with engine parameters (research).

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
from slingology_eis.limits import load_engine_config
from slingology_eis.cas import ECU_CLASSES, ecu_active_series, extract_engine_ecu_runs, takeoff_not_detected
from slingology_eis.phases import detect_phases

import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────
LOGS_DIR    = _TOOLKIT / "data" / "logs"
REPORTS_DIR = _TOOLKIT / "data" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Load engine config (reads from config.json or defaults to 916iS)
_engine_cfg = load_engine_config()

RPM_RUNNING = 500

CORR_PARAMS = [
    "rpm", "power_pct", "map_inhg", "map_hpa",
    "oil_press_psi", "oil_temp_f", "coolant_temp_f",
    "fuel_flow_gph", "fuel_press_psi",
    "egt1_f", "egt2_f", "egt3_f", "egt4_f", "egt_spread_f",
    "main_volts", "batt_amps", "efis_bkup_v", "nav_bkup_v",
    "ias_kt", "baro_alt_ft", "vs_fpm",
]


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
        n_ecu = int(ecu_active_series(df).sum())
        df = detect_phases(df, verbose=False)
        ext = extract_engine_ecu_runs(df, engine_config=_engine_cfg,
                                      takeoff_not_detected=takeoff_not_detected(df)[0])
        runs = ext.runs
        counts = {c: sum(1 for r in runs if r["classification"] == c) for c in ECU_CLASSES}

        all_runs.extend(runs)
        flight_summaries.append({
            "file": fname, "date": date, "total_rows": total,
            "ecu_rows": n_ecu, "ecu_pct": round(n_ecu / total * 100, 1),
            "counts": counts, "blips": ext.sub_threshold_blips, "lane_check": ext.lane_check,
            "aircraft": info.aircraft_ident, "engine_hours": info.engine_hours,
        })

        flag = "⚡" if counts["IN_FLIGHT"] else ("·" if counts["GROUND"] else "✓")
        print(f"\n  {flag} {fname}")
        print(f"     Date: {date}  |  Aircraft: {info.aircraft_ident}  "
              f"|  Engine hrs: {info.engine_hours}")
        print(f"     ENGINE ECU: {n_ecu} rows ({n_ecu/total*100:.1f}%)  —  "
              + "  ".join(f"{c}:{n}" for c, n in counts.items())
              + f"  blips:{ext.sub_threshold_blips}  lane check:{ext.lane_check}")
        for r in runs:
            print("       " + _run_line(r, with_file=False))

    # ── Aggregate ─────────────────────────────────────────────────────────────
    runs_df = pd.DataFrame(all_runs)
    print(f"\n{'=' * 70}")
    print("  AGGREGATE SUMMARY")
    print("=" * 70)
    print(f"\n  Flights analysed:        {len(flights)}")
    print(f"  Total ENGINE ECU runs:   {len(runs_df)}")
    for c in ECU_CLASSES:
        n = int((runs_df["classification"] == c).sum()) if len(runs_df) else 0
        print(f"    {c:<16} {n}")
    print(f"  Sub-threshold blips:     {sum(s['blips'] for s in flight_summaries)}")
    lc = {k: sum(1 for s in flight_summaries if s["lane_check"] == k) for k in ("both", "single", "none")}
    print(f"  Lane check per flight:   both {lc['both']}  single {lc['single']}  none {lc['none']}")

    events = runs_df[runs_df["classification"].isin(["GROUND", "IN_FLIGHT"])] if len(runs_df) else runs_df
    if len(events):
        print(f"\n  GROUND and IN_FLIGHT runs:")
        for _, r in events.iterrows():
            print("    " + _run_line(r.to_dict(), with_file=True))
    else:
        print(f"\n  No GROUND or IN_FLIGHT ENGINE ECU runs.")

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
        n = s["counts"]["IN_FLIGHT"]
        bar = "█" * n if n > 0 else "—"
        hrs = f"  {s['engine_hours']}h" if s["engine_hours"] else ""
        print(f"  {s['date']}  {n:2d} in-flight  {bar:<10}  lane check:{s['lane_check']}{hrs}  {s['file']}")

    # ── Save ──────────────────────────────────────────────────────────────────
    out_csv = REPORTS_DIR / "engine_ecu_runs.csv"
    runs_df.to_csv(out_csv, index=False)

    out_txt = REPORTS_DIR / "engine_ecu_report.txt"
    _write_text_report(flights, runs_df, flight_summaries, out_txt)

    print(f"\n  Saved: {out_csv}")
    print(f"  Saved: {out_txt}")
    print(f"\n{'=' * 70}\n")


def _run_line(r: dict, with_file: bool) -> str:
    """One run, factually: class, time, duration, deciding phase, oil-pressure
    gaps, lane-check pairing and co-active alerts."""
    oil = r.get("oil_nan_frac")
    oil_str = f"  oil_NaN:{oil * 100:.0f}%" if oil else ""
    unc = " (uncertain)" if r.get("phase_uncertain") else ""
    note = f"  {r['lane_check_note']}" if r.get("lane_check_note") else ""
    co = f"  co:{r['co_alerts']}" if r.get("co_alerts") else ""
    where = f"{r['source_file']}  {r['start_time']:%Y-%m-%d %H:%M:%S}" if with_file else f"{r['start_time']:%H:%M:%S}"
    return (f"[{r['classification']:<15}] {where}  {r['duration_s']:.0f}s  "
            f"phase {r['phase']}{unc}{oil_str}{note}{co}")


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
            "  " + "  ".join(f"{c}:{n}" for c, n in s["counts"].items())
            + f"  blips:{s['blips']}  lane check:{s['lane_check']}", "",
        ]
    lines += ["ALL RUNS:", "-" * 70]
    for _, row in runs_df.iterrows():
        lines.append("  " + _run_line(row.to_dict(), with_file=True))
    out_path.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
