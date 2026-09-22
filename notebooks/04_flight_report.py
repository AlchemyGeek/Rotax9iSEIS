"""
notebooks/04_flight_report.py
==============================
Per-flight pilot report with two-layer Analysis/Insight format.

Reads reports/baselines.json (written by 03_multi_flight_insights.py)
and insight_rules.json (toolkit root) to produce a plain-language
report for a single flight.

Usage
-----
    python notebooks/04_flight_report.py data/logs/log_20260527_200344_KSFF.csv
"""

import sys
import json
import math
from pathlib import Path
import contextlib
import io

_HERE    = Path(__file__).resolve().parent
_TOOLKIT = _HERE.parent
sys.path.insert(0, str(_TOOLKIT))

from slingology_eis.loader import load_log
from slingology_eis.phases import detect_phases, overboost_time
from slingology_eis.egt import egt_health
from slingology_eis.limits import check_exceedances, load_engine_config
from slingology_eis.cas import extract_engine_ecu_runs
from slingology_eis import topics

BASELINES_PATH    = _TOOLKIT / "data" / "reports" / "baselines.json"
RULES_PATH        = _TOOLKIT / "insight_rules.json"
MODELS_PATH = _TOOLKIT / "data" / "reports" / "models.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    if not path.exists():
        print(f"⚠  File not found: {path}")
        sys.exit(1)
    return json.loads(path.read_text())


def section(title: str):
    print(f"\n── {title} {'─' * max(0, 58 - len(title))}")


def analysis_line(text: str):
    print(f"  Analysis: {text}")


def insight_line(text: str):
    print(f"  Insight:  {text}")


def render_topic(result: dict):
    """Print a topic's analysis line followed by zero or more insight lines."""
    analysis_line(result["analysis"])
    for text in result["insights"]:
        insight_line(text)


def write_report(content: str, log_path: Path):
    out_path = _TOOLKIT / "data" / "reports" / f"report_{log_path.stem}.txt"
    out_path.write_text(content)
    print(f"  Report saved: {out_path}")

# ── Main ──────────────────────────────────────────────────────────────────────

def _main():
    if len(sys.argv) < 2:
        print("Usage: python 04_flight_report.py <path/to/log.csv>")
        sys.exit(1)

    log_arg = Path(sys.argv[1])
    if log_arg.is_absolute() or log_arg.exists():
        log_path = log_arg
    else:
        log_path = _TOOLKIT / "data" / "logs" / log_arg
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    baselines = _load_json(BASELINES_PATH)
    rules     = _load_json(RULES_PATH)
    b_data    = baselines.get("baselines", {})
    r_data    = rules.get("rules", {})

    # ── Load and prepare flight ───────────────────────────────────────────────
    df, info = load_log(log_path)
    df = detect_phases(df)
    engine_cfg  = load_engine_config()
    engine_name = engine_cfg.get("_metadata", {}).get("engine", "Rotax 916iS")

    flight_date = df["datetime"].iloc[0].date()
    flight_time = df["datetime"].iloc[0].strftime("%H:%M")
    icao = log_path.stem.split("_")[-1] if "_" in log_path.stem else "—"
    eh_start = f"{info.engine_hours}h" if info.engine_hours else "—"

    # Pull per-flight metrics from fleet_metrics.csv
    fm_path = _TOOLKIT / "data" / "reports" / "fleet_metrics.csv"
    fm_row = None
    if fm_path.exists():
        import pandas as _pd
        _fm = _pd.read_csv(fm_path)
        _match = _fm[_fm["source_file"] == log_path.name]
        if len(_match):
            fm_row = _match.iloc[0]

    duration_min = f"{fm_row['airborne_min']:.0f} min" if fm_row is not None and not math.isnan(
        fm_row["airborne_min"]) else "—"
    max_alt = f"{fm_row['max_altitude_ft']:,.0f} ft" if fm_row is not None and not math.isnan(
        fm_row["max_altitude_ft"]) else "—"
    max_ias = f"{fm_row['max_ias_kt']:.0f} kt" if fm_row is not None and not math.isnan(fm_row["max_ias_kt"]) else "—"
    fuel_used = f"{fm_row['fadec_gallons']:.1f} gal" if fm_row is not None and not math.isnan(
        fm_row["fadec_gallons"]) else "—"
    eh_end = f"{info.engine_hours + fm_row['duration_min'] / 60:.1f}h" \
        if fm_row is not None and info.engine_hours and not math.isnan(fm_row["duration_min"]) else "—"

    print("\n" + "═" * 70)
    print(f"  SLINGOLOGY EIS — FLIGHT REPORT")
    print(f"  {info.aircraft_ident}  |  {engine_name}")
    print(f"  Date:         {flight_date}  {flight_time}")
    print(f"  Airport:      {icao}")
    print(f"  Engine hrs:   {eh_start} → {eh_end}")
    print(f"  Duration:     {duration_min} airborne")
    print(f"  Max altitude: {max_alt}")
    print(f"  Max IAS:      {max_ias}")
    print(f"  Fuel used:    {fuel_used} (FADEC)")
    print(f"  Baselines:    {baselines.get('flight_count', '?')} flights  "
          f"({baselines.get('generated_at', '?')})")
    # Warn if no cruise phase detected — affects validity of cruise-based metrics
    has_cruise = fm_row is not None and not math.isnan(fm_row.get("phase_cruise_min", float("nan"))) \
                 and fm_row.get("phase_cruise_min", 0) > 0 \
        if fm_row is not None else False
    if not has_cruise:
        print(f"\n  ⚠ No stable cruise phase detected — EGT spread, fuel flow,")
        print(f"    and efficiency metrics will not be available for this flight.")

    print("═" * 70)

    # ── EGT SPREAD ───────────────────────────────────────────────────────────
    section("EGT SPREAD")
    egt = egt_health(df)
    spread = egt.get("spread_mean_f")
    b = b_data.get("egt_spread", {})
    rule_triggers = r_data.get("egt_spread", {}).get("triggers", [])
    enabled = r_data.get("egt_spread", {}).get("enabled", True)
    render_topic(topics.egt_spread(spread, egt.get("spread_hi_limit_f", 392), b, rule_triggers, enabled))

    # ── EGT4 ELEVATION ───────────────────────────────────────────────────────
    section("EGT4 ELEVATION")
    elev = egt.get("egt4_elevation_f")
    b = b_data.get("egt4_elevation", {})
    rule_triggers = r_data.get("egt4_elevation", {}).get("triggers", [])
    render_topic(topics.egt4_elevation(elev, b, rule_triggers))

    # ── CYLINDER RANK ─────────────────────────────────────────────────────────
    section("CYLINDER RANK")
    rank_stable = egt.get("rank_stable")
    rank_order = egt.get("rank_order", [])

    # Fleet stable count from already-loaded fleet_metrics
    if _fm is not None and "egt_rank_stable" in _fm.columns:
        total_count = int(_fm["egt_rank_stable"].notna().sum())
        stable_count = int(_fm["egt_rank_stable"].sum())
        fleet_note = f"Stable in {stable_count}/{total_count} fleet flights."
    else:
        fleet_note = ""
    render_topic(topics.cylinder_rank(rank_order, rank_stable, fleet_note))

    # ── OVERBOOST ─────────────────────────────────────────────────────────────
    section("OVERBOOST")
    ob = overboost_time(df, engine_cfg)
    ob_total  = ob.get("overboost_total_s", 0)
    ob_max    = ob.get("overboost_max_block_s", 0)
    ob_limit  = ob.get("overboost_limit_s", 300)
    render_topic(topics.overboost(ob_total, ob_max, ob_limit, ob.get("overboost_exceeded")))

    # ── TAKEOFF MAP ───────────────────────────────────────────────────────────
    section("TAKEOFF MAP")
    models = _load_json(MODELS_PATH) if MODELS_PATH.exists() else {}
    map_model = models.get("models", {}).get("takeoff_map", {})
    obs_map = float(fm_row["takeoff_map_inhg"]) \
        if fm_row is not None and "takeoff_map_inhg" in fm_row.index \
           and not math.isnan(fm_row["takeoff_map_inhg"]) else None
    obs_pa = float(fm_row["takeoff_pressure_alt_ft"]) \
        if fm_row is not None and "takeoff_pressure_alt_ft" in fm_row.index \
           and not math.isnan(fm_row["takeoff_pressure_alt_ft"]) else None
    obs_oat = float(fm_row["takeoff_oat_c"]) \
        if fm_row is not None and "takeoff_oat_c" in fm_row.index \
           and not math.isnan(fm_row["takeoff_oat_c"]) else None
    render_topic(topics.takeoff_map(obs_map, obs_pa, obs_oat, map_model))

    # ── OIL TEMPERATURE ───────────────────────────────────────────────────────
    section("OIL TEMPERATURE")
    oil_max = df["oil_temp_f"].max() if "oil_temp_f" in df.columns else None
    b = b_data.get("oil_temp_peak", {})
    rule_triggers = r_data.get("oil_temp_peak", {}).get("triggers", [])
    render_topic(topics.oil_temp_peak(oil_max, b, rule_triggers))

    # ── COOLANT TEMPERATURE ───────────────────────────────────────────────────
    section("COOLANT TEMPERATURE")
    coolant_max = df["coolant_temp_f"].max() if "coolant_temp_f" in df.columns else None
    b = b_data.get("coolant_temp_peak", {})
    rule_triggers = r_data.get("coolant_temp_peak", {}).get("triggers", [])
    render_topic(topics.coolant_temp_peak(coolant_max, b, rule_triggers))

    # ── OIL/COOLANT RATIO ────────────────────────────────────────────────────
    section("OIL/COOLANT RATIO")
    oc_ratio = float(fm_row["oil_coolant_ratio"]) \
        if fm_row is not None and not math.isnan(fm_row["oil_coolant_ratio"]) else None
    b = b_data.get("oil_coolant_ratio", {})
    rule_triggers = r_data.get("oil_coolant_ratio", {}).get("triggers", [])
    render_topic(topics.oil_coolant_ratio(oc_ratio, b, rule_triggers))

    # ── CRUISE EFFICIENCY ─────────────────────────────────────────────────────
    section("CRUISE EFFICIENCY")
    b = b_data.get("cruise_efficiency", {})
    rule_triggers = r_data.get("cruise_efficiency", {}).get("triggers", [])
    # Pull from fleet_metrics for this flight if available
    fm_path = _TOOLKIT / "data" / "reports" / "fleet_metrics.csv"
    nmpg = None
    if fm_path.exists():
        import pandas as pd
        fm = pd.read_csv(fm_path)
        match = fm[fm["source_file"] == log_path.name]
        if len(match):
            nmpg = match["cruise_nmpg"].iloc[0]
            nmpg = None if (isinstance(nmpg, float) and math.isnan(nmpg)) else nmpg
    render_topic(topics.cruise_efficiency(nmpg, b, rule_triggers))

    # ── CRUISE FUEL FLOW ─────────────────────────────────────────────────────
    section("CRUISE FUEL FLOW")
    fuel_flow = float(fm_row["cruise_fuel_flow_gph"]) \
        if fm_row is not None and not math.isnan(fm_row["cruise_fuel_flow_gph"]) else None
    b = b_data.get("cruise_fuel_flow", {})
    rule_triggers = r_data.get("cruise_fuel_flow", {}).get("triggers", [])
    this_da = float(fm_row["cruise_da_ft"]) \
        if fm_row is not None and not math.isnan(fm_row["cruise_da_ft"]) else None
    da_b = b_data.get("cruise_da_ft", {})
    render_topic(topics.cruise_fuel_flow(
        fuel_flow, b, rule_triggers,
        this_da=this_da, fleet_da_avg=da_b.get("mean"), fleet_da_std=da_b.get("std"),
    ))

    # ── ENGINE ECU ────────────────────────────────────────────────────────────
    section("ENGINE ECU")
    ecu_runs = extract_engine_ecu_runs(df, engine_config=engine_cfg)
    ecu_result = topics.engine_ecu_inflight(ecu_runs)
    analysis_line(ecu_result["analysis"])
    if ecu_result["events"]:
        for event in ecu_result["events"]:
            co = event["co_alerts"]
            direct = set(event["direct_correlation_alerts"])
            oil_nan = event["oil_nan_frac"]
            oil_str = f"  oil_NaN:{oil_nan * 100:.0f}%" if oil_nan is not None else ""
            print(f"    ⚡ {event['start_time']:%H:%M:%S}  {event['duration_s']:.0f}s{oil_str}")
            if co:
                for alert in co:
                    if alert in direct:
                        insight_line(
                            f"⚠ Co-active: {alert} — only IN-FLIGHT event with a "
                            f"direct engine-parameter correlation. Verify oil pressure "
                            f"was genuine, not a CAN dropout."
                        )
                    else:
                        print(f"      · Co-active: {alert}")
            else:
                print(
                    "      · No co-active alerts — ENGINE ECU isolated "
                    "→ CAN fault, not ECU hardware."
                )
        print(
            "    Run 02_engine_ecu_correlation.py for full CAN bus "
            "pattern analysis and recommended actions."
        )

    # ── CLIMB THERMAL RATE ───────────────────────────────────────────────────
    section("CLIMB THERMAL RATE")
    oil_rise = float(fm_row["climb_oil_rise_f_per_min"]) \
        if fm_row is not None and "climb_oil_rise_f_per_min" in fm_row.index \
           and not math.isnan(fm_row["climb_oil_rise_f_per_min"]) else None
    b = b_data.get("climb_thermal_rate", {})
    rule_triggers = r_data.get("climb_thermal_rate", {}).get("triggers", [])
    render_topic(topics.climb_thermal_rate(oil_rise, b, rule_triggers))

    # ── LIMIT EXCEEDANCES ─────────────────────────────────────────────────────
    section("LIMIT EXCEEDANCES")
    exceedances = check_exceedances(df, engine_cfg)
    render_topic(topics.limit_exceedances(exceedances))

    print("\n" + "═" * 70 + "\n")

def main():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        _main()
    content = buffer.getvalue()
    print(content, end="")
    log_path = Path(sys.argv[1])
    write_report(content, log_path)


if __name__ == "__main__":
    main()