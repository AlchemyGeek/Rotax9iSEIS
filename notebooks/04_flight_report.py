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
from datetime import date
from typing import Optional

_HERE    = Path(__file__).resolve().parent
_TOOLKIT = _HERE.parent
sys.path.insert(0, str(_TOOLKIT))

from slingology_eis.loader import load_log
from slingology_eis.phases import detect_phases, overboost_time
from slingology_eis.egt import egt_health
from slingology_eis.limits import check_exceedances, load_engine_config
from slingology_eis.cas import parse_cas
from slingology_eis.cas import extract_engine_ecu_runs

BASELINES_PATH    = _TOOLKIT / "data" / "reports" / "baselines.json"
RULES_PATH        = _TOOLKIT / "insight_rules.json"
MODELS_PATH = _TOOLKIT / "data" / "reports" / "models.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    if not path.exists():
        print(f"⚠  File not found: {path}")
        sys.exit(1)
    return json.loads(path.read_text())


def _z_score(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0
    return (value - mean) / std


def _baseline_triggered(value, b: dict, rule: dict) -> tuple[bool, str]:
    """Check baseline_deviation trigger. Returns (triggered, insight_text)."""
    if value is None or b.get("mean") is None or b.get("std") is None:
        return False, ""
    z = _z_score(value, b["mean"], b["std"])
    threshold = rule.get("z_score_threshold", 2.0)
    if abs(z) >= threshold:
        direction = "above" if z > 0 else "below"
        return True, f"{'⚠' if z > 0 else '↓'} {abs(z):.1f} std devs {direction} your personal average."
    return False, ""


def _trend_triggered(b: dict, rule: dict) -> tuple[bool, str]:
    """Check trend trigger. Returns (triggered, insight_text)."""
    t = b.get("trend", {})
    if not t or t.get("direction") in (None, "insufficient data", "flat / no clear trend"):
        return False, ""
    r2 = t.get("r_squared", 0)
    n  = t.get("n", 0)
    if r2 < rule.get("r2_min", 0.5) or n < rule.get("n_min", 10):
        return False, ""
    if t["direction"] == rule.get("direction"):
        return True, (f"⚠ Trending {t['direction']} over engine hours "
                      f"(slope={t['slope']:+.3f}/hr, R²={r2:.2f}, n={n}).")
    return False, ""


def _confidence_note(b: dict) -> str:
    n = b.get("n", 0)
    if n < 3:
        return f" [still building baseline — n={n}]"
    if n < 10:
        return f" [low confidence — n={n}]"
    return ""


def section(title: str):
    print(f"\n── {title} {'─' * max(0, 58 - len(title))}")


def analysis_line(text: str):
    print(f"  Analysis: {text}")


def insight_line(text: str):
    print(f"  Insight:  {text}")

def write_report(content: str, log_path: Path):
    out_path = _TOOLKIT / "data" / "reports" / f"report_{log_path.stem}.txt"
    out_path.write_text(content)
    print(f"  Report saved: {out_path}")

def _predict_map(model: dict, pressure_alt_ft: float, oat_c: float) -> Optional[float]:
    """Predict MAP from the linear regression model."""
    coeffs = model.get("coefficients", {})
    if not coeffs:
        return None
    return (
        coeffs.get("intercept", 0)
        + coeffs.get("pressure_alt_ft", 0) * pressure_alt_ft
        + coeffs.get("oat_c", 0) * oat_c
    )

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

    if spread is not None and b.get("mean") is not None:
        note = _confidence_note(b)
        analysis_line(
            f"Cruise mean {spread:.0f}°F. "
            f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
            f"({b['n']} flights{note}). OM limit: {egt.get('spread_hi_limit_f', 392):.0f}°F."
        )
        insights = []
        for rule in rule_triggers:
            if not r_data.get("egt_spread", {}).get("enabled", True):
                continue
            if rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(spread, b, rule)
                if triggered:
                    insights.append(text)
            elif rule["type"] == "trend":
                triggered, text = _trend_triggered(b, rule)
                if triggered:
                    insights.append(text)
        for i in insights:
            insight_line(i)
    else:
        analysis_line("Insufficient cruise data for EGT spread.")

    # ── EGT4 ELEVATION ───────────────────────────────────────────────────────
    section("EGT4 ELEVATION")
    elev = egt.get("egt4_elevation_f")
    b = b_data.get("egt4_elevation", {})
    rule_triggers = r_data.get("egt4_elevation", {}).get("triggers", [])

    if elev is not None and b.get("mean") is not None:
        note = _confidence_note(b)
        analysis_line(
            f"EGT4 is {elev:+.0f}°F vs cylinders 1–3. "
            f"Your average: {b['mean']:+.0f}°F ± {b['std']:.0f}°F "
            f"({b['n']} flights{note})."
        )
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(elev, b, rule)
                if triggered:
                    insight_line(text)
    else:
        analysis_line("EGT4 elevation not available.")

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

    if rank_order:
        hottest = rank_order[0].replace("egt", "EGT").replace("_f", "").upper()
        if rank_stable:
            analysis_line(
                f"Hottest cylinder this flight: {hottest} (stable throughout cruise). "
                f"{fleet_note}"
            )
        else:
            analysis_line(
                f"Cylinder rank unstable this flight — hottest cylinder changed during cruise. "
                f"{fleet_note}"
            )
            insight_line(
                "⚠ Rank instability is unusual for this engine — possible early "
                "injector or ignition imbalance. Compare per-cylinder EGT means "
                "in script 01."
            )
    else:
        analysis_line("Insufficient cruise data for cylinder rank analysis.")

    # ── OVERBOOST ─────────────────────────────────────────────────────────────
    section("OVERBOOST")
    ob = overboost_time(df, engine_cfg)
    ob_total  = ob.get("overboost_total_s", 0)
    ob_max    = ob.get("overboost_max_block_s", 0)
    ob_limit  = ob.get("overboost_limit_s", 300)
    b = b_data.get("overboost_time", {})

    analysis_line(
        f"Max continuous block: {ob_max}s. Total this flight: {ob_total}s. "
        f"OM limit: {ob_limit}s."
    )
    if ob.get("overboost_exceeded"):
        insight_line(f"⚠ Exceeded OM {ob_limit}s limit by {ob_max - ob_limit}s.")
    elif ob_max >= 240:
        insight_line(f"⚠ Close call — {ob_limit - ob_max}s below the OM limit. "
                     f"Pull back to climb power promptly after takeoff.")

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

    if obs_map is None:
        analysis_line("No takeoff MAP data available — "
                      "flight may lack a TAKEOFF phase with RPM ≥ 5,500.")
    else:
        n_model = map_model.get("n", 0)
        conf = map_model.get("confidence", "")
        pa_str = f"{obs_pa:,.0f} ft PA" if obs_pa is not None else "unknown PA"
        oat_str = f"{obs_oat:.0f}°C" if obs_oat is not None else "unknown OAT"

        if n_model < 5:
            analysis_line(
                f"Observed MAP at takeoff: {obs_map:.1f} inHg at {pa_str}, {oat_str}. "
                f"Still collecting data to build your personal MAP baseline "
                f"(n={n_model} — need 5 minimum for first model fit)."
            )
        else:
            exp_map = _predict_map(map_model, obs_pa, obs_oat) \
                if obs_pa is not None and obs_oat is not None else None
            r2 = map_model.get("r_squared", 0)
            if exp_map is not None:
                delta = obs_map - exp_map
                analysis_line(
                    f"Observed MAP at takeoff: {obs_map:.1f} inHg at {pa_str}, {oat_str}. "
                    f"Model expected: {exp_map:.1f} inHg "
                    f"(n={n_model}, {conf.split(' ')[0]}, R²={r2:.2f})."
                )
                if abs(delta) >= 1.5:
                    direction = "below" if delta < 0 else "above"
                    insight_line(
                        f"⚠ {abs(delta):.1f} inHg {direction} model — "
                        f"{'possible turbo underperformance, monitor trend.' if delta < 0 else 'above model — verify sensor.'}"
                    )
            else:
                analysis_line(
                    f"Observed MAP at takeoff: {obs_map:.1f} inHg. "
                    f"Model available (n={n_model}) but PA/OAT missing for prediction."
                )

    # ── OIL TEMPERATURE ───────────────────────────────────────────────────────
    section("OIL TEMPERATURE")
    oil_max = df["oil_temp_f"].max() if "oil_temp_f" in df.columns else None
    b = b_data.get("oil_temp_peak", {})
    rule_triggers = r_data.get("oil_temp_peak", {}).get("triggers", [])

    if oil_max is not None and b.get("mean") is not None:
        note = _confidence_note(b)
        analysis_line(
            f"Peak {oil_max:.0f}°F. "
            f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
            f"({b['n']} flights{note}). OM limit: 248°F."
        )
        for rule in rule_triggers:
            if rule["type"] == "threshold" and oil_max > rule.get("limit", 248):
                insight_line(f"⚠ Exceeded OM limit of {rule['limit']}°F.")
            elif rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(oil_max, b, rule)
                if triggered:
                    insight_line(text)
    else:
        analysis_line("Oil temperature data not available.")

    for rule in rule_triggers:
        if rule["type"] == "threshold" and oil_max > rule.get("limit", 248):
            insight_line(f"⚠ Exceeded OM limit of {rule['limit']}°F.")
        elif rule["type"] == "baseline_deviation":
            triggered, text = _baseline_triggered(oil_max, b, rule)
            if triggered:
                insight_line(text)

    # ── COOLANT TEMPERATURE ───────────────────────────────────────────────────
    section("COOLANT TEMPERATURE")
    coolant_max = df["coolant_temp_f"].max() if "coolant_temp_f" in df.columns else None
    b = b_data.get("coolant_temp_peak", {})
    rule_triggers = r_data.get("coolant_temp_peak", {}).get("triggers", [])

    if coolant_max is not None and b.get("mean") is not None:
        note = _confidence_note(b)
        analysis_line(
            f"Peak {coolant_max:.0f}°F. "
            f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
            f"({b['n']} flights{note}). OM limit: 248°F."
        )
        for rule in rule_triggers:
            if rule["type"] == "threshold" and coolant_max > rule.get("limit", 248):
                insight_line(f"⚠ Exceeded OM limit of {rule['limit']}°F.")
            elif rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(coolant_max, b, rule)
                if triggered:
                    insight_line(text)
    else:
        analysis_line("Coolant temperature data not available.")

    # ── OIL/COOLANT RATIO ────────────────────────────────────────────────────
    section("OIL/COOLANT RATIO")
    oc_ratio = float(fm_row["oil_coolant_ratio"]) \
        if fm_row is not None and not math.isnan(fm_row["oil_coolant_ratio"]) else None
    b = b_data.get("oil_coolant_ratio", {})
    rule_triggers = r_data.get("oil_coolant_ratio", {}).get("triggers", [])

    if oc_ratio is not None and b.get("mean") is not None:
        note = _confidence_note(b)
        analysis_line(
            f"Oil/coolant ratio this flight: {oc_ratio:.2f}. "
            f"Your average: {b['mean']:.2f} ± {b['std']:.2f} "
            f"({b['n']} flights{note})."
        )
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(oc_ratio, b, rule)
                if triggered:
                    insight_line(text)
    else:
        analysis_line("Oil/coolant ratio not available for this flight.")

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

    if nmpg is not None and b.get("mean") is not None:
        note = _confidence_note(b)
        analysis_line(
            f"{nmpg:.1f} nm/gal this flight. "
            f"Your average: {b['mean']:.1f} ± {b['std']:.1f} nm/gal "
            f"({b['n']} flights{note}, DA-stratified)."
        )
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(nmpg, b, rule)
                if triggered:
                    insight_line(text)
            elif rule["type"] == "trend":
                triggered, text = _trend_triggered(b, rule)
                if triggered:
                    insight_line(text)
    elif b.get("mean") is None:
        analysis_line("Still building your cruise efficiency baseline.")
    else:
        analysis_line("No cruise efficiency data for this flight.")

    # ── CRUISE FUEL FLOW ─────────────────────────────────────────────────────
    section("CRUISE FUEL FLOW")
    fuel_flow = float(fm_row["cruise_fuel_flow_gph"]) \
        if fm_row is not None and not math.isnan(fm_row["cruise_fuel_flow_gph"]) else None
    b = b_data.get("cruise_fuel_flow", {})
    rule_triggers = r_data.get("cruise_fuel_flow", {}).get("triggers", [])

    if fuel_flow is not None and b.get("mean") is not None:
        note = _confidence_note(b)

        # DA context for fuel flow comparison
        this_da = float(fm_row["cruise_da_ft"]) \
            if fm_row is not None and not math.isnan(fm_row["cruise_da_ft"]) else None
        fleet_da_mean = float(b_data.get("cruise_efficiency", {}).get("mean", 0)) \
            if "cruise_efficiency" in b_data else None

        # Compute fleet average DA from raw data points
        ce_raw = b_data.get("cruise_efficiency", {}).get("raw", [])
        fleet_da_vals = [r["da_band"] for r in ce_raw if r.get("da_band") is not None]
        da_b = b_data.get("cruise_da_ft", {})
        fleet_da_avg = da_b.get("mean")
        fleet_da_std = da_b.get("std")

        da_note = ""
        da_high = False
        if this_da is not None and fleet_da_avg is not None and fleet_da_std:
            da_z = (this_da - fleet_da_avg) / fleet_da_std
            da_note = (f" at cruise DA {this_da:,.0f} ft "
                       f"(fleet avg {fleet_da_avg:,.0f} ft)")
            da_high = da_z > 1.0

        analysis_line(
            f"{fuel_flow:.1f} gph this flight{da_note}. "
            f"Your average: {b['mean']:.1f} ± {b['std']:.1f} gph "
            f"({b['n']} flights{note}, all altitudes blended)."
        )
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(fuel_flow, b, rule)
                if triggered:
                    if da_high:
                        insight_line(
                            text + " Note: this flight's cruise DA was "
                                   "significantly higher than your typical cruise — "
                                   "altitude and power setting affect fuel flow. "
                                   "A power/altitude model is needed for a fully valid comparison."
                        )
                    else:
                        insight_line(text)
    elif b.get("mean") is None:
        analysis_line("Still building your cruise fuel flow baseline.")
    else:
        analysis_line("No cruise fuel flow data for this flight.")

    # ── ENGINE ECU ────────────────────────────────────────────────────────────
    section("ENGINE ECU")
    ecu_runs = extract_engine_ecu_runs(df, engine_config=engine_cfg)
    inflight = [r for r in ecu_runs if r["classification"] == "IN_FLIGHT"]

    if not inflight:
        analysis_line(
            "No IN-FLIGHT ENGINE ECU events — all occurrences are "
            "expected FADEC behaviour (POWERUP, LANE_CHECK, SHUTDOWN)."
        )
    else:
        analysis_line(
            f"{len(inflight)} IN-FLIGHT ENGINE ECU event(s) detected "
            f"— requires investigation."
        )
        for r in inflight:
            co = r.get("co_alerts", [])
            oil_nan = r.get("oil_nan_frac")
            oil_str = f"  oil_NaN:{oil_nan * 100:.0f}%" if oil_nan is not None else ""
            print(f"    ⚡ {r['start_time']:%H:%M:%S}  {r['duration_s']:.0f}s{oil_str}")
            if co:
                for alert in co:
                    if alert == "OIL PRESS":
                        insight_line(
                            f"⚠ Co-active: OIL PRESS — only IN-FLIGHT event with a "
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

    if oil_rise is not None and b.get("mean") is not None:
        note = _confidence_note(b)
        analysis_line(
            f"Oil temp rose {oil_rise:.1f}°F/min during climb. "
            f"Your average: {b['mean']:.1f} ± {b['std']:.1f}°F/min "
            f"({b['n']} flights{note})."
        )
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = _baseline_triggered(oil_rise, b, rule)
                if triggered:
                    insight_line(text)
    else:
        analysis_line("Insufficient climb data for thermal rate — "
                      "short or pattern-work flights don't contribute here.")

    # ── LIMIT EXCEEDANCES ─────────────────────────────────────────────────────
    section("LIMIT EXCEEDANCES")
    exceedances = check_exceedances(df, engine_cfg)
    if exceedances:
        analysis_line(f"{len(exceedances)} OM hard-limit exceedance(s) this flight:")
        for exc in exceedances:
            insight_line(f"⚠ {exc}")
    else:
        analysis_line("No OM hard-limit exceedances this flight.")

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