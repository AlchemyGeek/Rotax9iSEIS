"""
notebooks/01_first_flight_analysis.py
======================================
Deep-dive diagnostic report for a SINGLE flight log.

Runs every analysis module (phases, limits, EGT health, fuel, CAS alerts)
against one log file and prints a full narrative report — the same kind
of read you'd want when debriefing a specific flight.

Usage
-----
    # Analyse a specific file by name (looked up in data/logs/):
    python notebooks/01_first_flight_analysis.py log_20260518_195524_KAWO.csv

    # Or pass a full/relative path:
    python notebooks/01_first_flight_analysis.py ../data/logs/some_file.csv

    # No argument: defaults to the most recently modified log in data/logs/
    python notebooks/01_first_flight_analysis.py

For analysis ACROSS multiple flights (trends, baselines, fleet-style
aggregation), see 02_engine_ecu_correlation.py and 03_multi_flight_insights.py.
"""

import sys
import argparse
from pathlib import Path

_HERE    = Path(__file__).resolve().parent
_TOOLKIT = _HERE.parent
sys.path.insert(0, str(_TOOLKIT))

from slingology_eis.loader import load_log, log_summary
from slingology_eis.limits import limits_report
from slingology_eis.phases import detect_phases, phase_summary, overboost_time
from slingology_eis.egt   import egt_report
from slingology_eis.fuel  import fuel_report
from slingology_eis.cas   import cas_report
from slingology_eis.climb import climb_report

LOGS_DIR = _TOOLKIT / "data" / "logs"


def resolve_log_path(arg: str | None) -> Path:
    """
    Resolve the log file to analyse:
      1. No argument          → most recently modified *.csv in data/logs/
      2. Bare filename         → looked up inside data/logs/
      3. Relative/absolute path → used as-is
    """
    if arg is None:
        candidates = sorted(LOGS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise FileNotFoundError(f"No .csv files found in {LOGS_DIR}")
        chosen = candidates[-1]
        print(f"(no file specified — using most recent: {chosen.name})\n")
        return chosen

    p = Path(arg)
    if p.exists():
        return p

    candidate = LOGS_DIR / arg
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        f"Could not find '{arg}' as a path or inside {LOGS_DIR}"
    )


def main():
    parser = argparse.ArgumentParser(description="Single-flight diagnostic report")
    parser.add_argument(
        "log", nargs="?", default=None,
        help="Log filename (looked up in data/logs/) or a full path. "
             "If omitted, uses the most recently modified log."
    )
    parser.add_argument(
        "--field-elev", type=float, default=None,
        help="Departure field elevation in feet, for AGL approximation. "
             "Default: auto-estimated from the log's own ground-ops data."
    )
    args = parser.parse_args()

    log_path = resolve_log_path(args.log)

    print("=" * 65)
    print("  SLINGOLOGY EIS — Flight Analysis")
    print("  Log:", log_path.name)
    print("=" * 65)

    df, info = load_log(log_path)

    print(f"\n── Airframe Info ─────────────────────────────────────────────")
    print(f"  Aircraft:       {info.aircraft_ident}")
    print(f"  Product:        {info.product}")
    print(f"  SW Version:     {info.software_version}")
    print(f"  Airframe hrs:   {info.airframe_hours}")
    print(f"  Engine hrs:     {info.engine_hours}")
    print(f"  Source format:  {info.source_format}")

    s = log_summary(df, info)
    print(f"\n── Flight Summary ────────────────────────────────────────────")
    print(f"  Date:           {s['date']}")
    print(f"  Duration:       {s['duration_min']:.0f} min")
    print(f"  Airborne:       {s['airborne_min']:.1f} min  ({s['airborne_rows']} rows)")
    print(f"  Max IAS:        {df['ias_kt'].max():.0f} kt")
    print(f"  Max baro alt:   {df['baro_alt_ft'].max():.0f} ft")
    print(f"  Logging rows:   {s['rows']}  interval: {s['interval_s']:.0f}s")

    print(f"\n── Flight Phases ─────────────────────────────────────────────")
    df = detect_phases(df, field_elev_ft=args.field_elev, verbose=True)
    ps = phase_summary(df)
    print(ps[["phase", "start", "duration_s", "rpm_mean", "power_pct_mean",
              "ias_kt_mean", "fuel_flow_gph_mean"]].to_string(index=False))

    ob = overboost_time(df)
    print(f"\n── Overboost ─────────────────────────────────────────────────")
    print(f"  Total time at RPM>5500 or Power>100%: {ob['overboost_total_s']}s")
    print(f"  Max continuous block:                 {ob['overboost_max_block_s']}s")
    print(f"  5-min limit exceeded:                 {ob['overboost_exceeded']}")

    print(f"\n── Operating Limits ──────────────────────────────────────────")
    print(limits_report(df))

    print(f"\n{egt_report(df)}")
    print(f"\n{fuel_report(df)}")
    print(f"\n{climb_report(df)}")
    print(f"\n{cas_report(df)}")

    print(f"\n── EGT Summary by Phase ──────────────────────────────────────")
    for phase in ["CLIMB", "CRUISE", "DESCENT"]:
        sub = df[df["phase"] == phase]
        if len(sub) == 0:
            continue
        egts = sub[["egt1_f", "egt2_f", "egt3_f", "egt4_f"]].dropna()
        if len(egts) == 0:
            continue
        means       = egts.mean()
        spread_mean = (egts.max(axis=1) - egts.min(axis=1)).mean()
        print(f"  {phase:<14} "
              f"EGT1={means['egt1_f']:.0f}°F  "
              f"EGT2={means['egt2_f']:.0f}°F  "
              f"EGT3={means['egt3_f']:.0f}°F  "
              f"EGT4={means['egt4_f']:.0f}°F  "
              f"spread={spread_mean:.0f}°F")

    print(f"\n{'=' * 65}")
    print("  Analysis complete.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
