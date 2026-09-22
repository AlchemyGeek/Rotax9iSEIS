"""
topics.py — per-flight topic analysis and insight evaluation.

Each topic function is a pure computation: given a flight's own values
plus its personal baseline/rules, it returns the report's two-layer
content — {"analysis": str, "insights": list[str]} — with no printing.
notebooks/04_flight_report.py is a thin renderer over these.

This mirrors Spec 01 §8.5's TopicResult/Insight shape at the level Stage
2 needs (structured analysis text, zero-or-more insight strings); the
full typed contract (templates, severity enums, evidence refs) is Stage
3 work, deliberately not built here — Spec 01 Q3 leaves the eventual
Topic plugin interface to emerge from doing this extraction for real,
not to be designed upfront.
"""
from __future__ import annotations

from typing import Optional

from .cas import analyze_inflight_pattern


# ── Shared rule-evaluation helpers (moved from notebook 04) ──────────────────

def z_score(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0
    return (value - mean) / std


def baseline_triggered(value, b: dict, rule: dict) -> tuple[bool, str]:
    """Check a baseline_deviation trigger. Returns (triggered, insight_text)."""
    if value is None or b.get("mean") is None or b.get("std") is None:
        return False, ""
    z = z_score(value, b["mean"], b["std"])
    threshold = rule.get("z_score_threshold", 2.0)
    if abs(z) >= threshold:
        direction = "above" if z > 0 else "below"
        return True, f"{'⚠' if z > 0 else '↓'} {abs(z):.1f} std devs {direction} your personal average."
    return False, ""


def trend_triggered(b: dict, rule: dict) -> tuple[bool, str]:
    """Check a trend trigger. Returns (triggered, insight_text)."""
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


def confidence_note(b: dict) -> str:
    n = b.get("n", 0)
    if n < 3:
        return f" [still building baseline — n={n}]"
    if n < 10:
        return f" [low confidence — n={n}]"
    return ""


def predict_takeoff_map(model: dict, pressure_alt_ft: float, oat_c: float) -> Optional[float]:
    """Predict MAP from the takeoff-MAP linear regression model."""
    coeffs = model.get("coefficients", {})
    if not coeffs:
        return None
    return (
        coeffs.get("intercept", 0)
        + coeffs.get("pressure_alt_ft", 0) * pressure_alt_ft
        + coeffs.get("oat_c", 0) * oat_c
    )


# ── Topics ─────────────────────────────────────────────────────────────────

def egt_spread(spread, spread_hi_limit_f: float, b: dict, rule_triggers: list, enabled: bool = True) -> dict:
    if spread is None or b.get("mean") is None:
        return {"analysis": "Insufficient cruise data for EGT spread.", "insights": []}
    note = confidence_note(b)
    analysis = (
        f"Cruise mean {spread:.0f}°F. "
        f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
        f"({b['n']} flights{note}). OM limit: {spread_hi_limit_f:.0f}°F."
    )
    insights = []
    if enabled:
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = baseline_triggered(spread, b, rule)
                if triggered:
                    insights.append(text)
            elif rule["type"] == "trend":
                triggered, text = trend_triggered(b, rule)
                if triggered:
                    insights.append(text)
    return {"analysis": analysis, "insights": insights}


def egt4_elevation(elev, b: dict, rule_triggers: list) -> dict:
    if elev is None or b.get("mean") is None:
        return {"analysis": "EGT4 elevation not available.", "insights": []}
    note = confidence_note(b)
    analysis = (
        f"EGT4 is {elev:+.0f}°F vs cylinders 1–3. "
        f"Your average: {b['mean']:+.0f}°F ± {b['std']:.0f}°F "
        f"({b['n']} flights{note})."
    )
    insights = []
    for rule in rule_triggers:
        if rule["type"] == "baseline_deviation":
            triggered, text = baseline_triggered(elev, b, rule)
            if triggered:
                insights.append(text)
    return {"analysis": analysis, "insights": insights}


def cylinder_rank(rank_order: list, rank_stable: Optional[bool], fleet_note: str) -> dict:
    if not rank_order:
        return {"analysis": "Insufficient cruise data for cylinder rank analysis.", "insights": []}
    hottest = rank_order[0].replace("egt", "EGT").replace("_f", "").upper()
    if rank_stable:
        analysis = (
            f"Hottest cylinder this flight: {hottest} (stable throughout cruise). "
            f"{fleet_note}"
        )
        return {"analysis": analysis, "insights": []}
    analysis = (
        f"Cylinder rank unstable this flight — hottest cylinder changed during cruise. "
        f"{fleet_note}"
    )
    insights = [
        "⚠ Rank instability is unusual for this engine — possible early "
        "injector or ignition imbalance. Compare per-cylinder EGT means "
        "in script 01."
    ]
    return {"analysis": analysis, "insights": insights}


def overboost(ob_total, ob_max, ob_limit, ob_exceeded: bool) -> dict:
    analysis = (
        f"Max continuous block: {ob_max}s. Total this flight: {ob_total}s. "
        f"OM limit: {ob_limit}s."
    )
    insights = []
    if ob_exceeded:
        insights.append(f"⚠ Exceeded OM {ob_limit}s limit by {ob_max - ob_limit}s.")
    elif ob_max >= 240:
        insights.append(f"⚠ Close call — {ob_limit - ob_max}s below the OM limit. "
                         f"Pull back to climb power promptly after takeoff.")
    return {"analysis": analysis, "insights": insights}


def takeoff_map(obs_map, obs_pa, obs_oat, map_model: dict) -> dict:
    if obs_map is None:
        return {
            "analysis": "No takeoff MAP data available — "
                        "flight may lack a TAKEOFF phase with RPM ≥ 5,500.",
            "insights": [],
        }
    n_model = map_model.get("n", 0)
    conf = map_model.get("confidence", "")
    pa_str = f"{obs_pa:,.0f} ft PA" if obs_pa is not None else "unknown PA"
    oat_str = f"{obs_oat:.0f}°C" if obs_oat is not None else "unknown OAT"
    insights = []

    if n_model < 5:
        analysis = (
            f"Observed MAP at takeoff: {obs_map:.1f} inHg at {pa_str}, {oat_str}. "
            f"Still collecting data to build your personal MAP baseline "
            f"(n={n_model} — need 5 minimum for first model fit)."
        )
        return {"analysis": analysis, "insights": insights}

    exp_map = predict_takeoff_map(map_model, obs_pa, obs_oat) \
        if obs_pa is not None and obs_oat is not None else None
    r2 = map_model.get("r_squared", 0)
    if exp_map is not None:
        delta = obs_map - exp_map
        analysis = (
            f"Observed MAP at takeoff: {obs_map:.1f} inHg at {pa_str}, {oat_str}. "
            f"Model expected: {exp_map:.1f} inHg "
            f"(n={n_model}, {conf.split(' ')[0]}, R²={r2:.2f})."
        )
        if abs(delta) >= 1.5:
            direction = "below" if delta < 0 else "above"
            insights.append(
                f"⚠ {abs(delta):.1f} inHg {direction} model — "
                f"{'possible turbo underperformance, monitor trend.' if delta < 0 else 'above model — verify sensor.'}"
            )
    else:
        analysis = (
            f"Observed MAP at takeoff: {obs_map:.1f} inHg. "
            f"Model available (n={n_model}) but PA/OAT missing for prediction."
        )
    return {"analysis": analysis, "insights": insights}


def oil_temp_peak(oil_max, b: dict, rule_triggers: list) -> dict:
    if oil_max is None or b.get("mean") is None:
        return {"analysis": "Oil temperature data not available.", "insights": []}
    note = confidence_note(b)
    analysis = (
        f"Peak {oil_max:.0f}°F. "
        f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
        f"({b['n']} flights{note}). OM limit: 248°F."
    )
    insights = []
    for rule in rule_triggers:
        if rule["type"] == "threshold" and oil_max > rule.get("limit", 248):
            insights.append(f"⚠ Exceeded OM limit of {rule['limit']}°F.")
        elif rule["type"] == "baseline_deviation":
            triggered, text = baseline_triggered(oil_max, b, rule)
            if triggered:
                insights.append(text)
    return {"analysis": analysis, "insights": insights}


def coolant_temp_peak(coolant_max, b: dict, rule_triggers: list) -> dict:
    if coolant_max is None or b.get("mean") is None:
        return {"analysis": "Coolant temperature data not available.", "insights": []}
    note = confidence_note(b)
    analysis = (
        f"Peak {coolant_max:.0f}°F. "
        f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
        f"({b['n']} flights{note}). OM limit: 248°F."
    )
    insights = []
    for rule in rule_triggers:
        if rule["type"] == "threshold" and coolant_max > rule.get("limit", 248):
            insights.append(f"⚠ Exceeded OM limit of {rule['limit']}°F.")
        elif rule["type"] == "baseline_deviation":
            triggered, text = baseline_triggered(coolant_max, b, rule)
            if triggered:
                insights.append(text)
    return {"analysis": analysis, "insights": insights}


def oil_coolant_ratio(oc_ratio, b: dict, rule_triggers: list) -> dict:
    if oc_ratio is None or b.get("mean") is None:
        return {"analysis": "Oil/coolant ratio not available for this flight.", "insights": []}
    note = confidence_note(b)
    analysis = (
        f"Oil/coolant ratio this flight: {oc_ratio:.2f}. "
        f"Your average: {b['mean']:.2f} ± {b['std']:.2f} "
        f"({b['n']} flights{note})."
    )
    insights = []
    for rule in rule_triggers:
        if rule["type"] == "baseline_deviation":
            triggered, text = baseline_triggered(oc_ratio, b, rule)
            if triggered:
                insights.append(text)
    return {"analysis": analysis, "insights": insights}


def cruise_efficiency(nmpg, b: dict, rule_triggers: list) -> dict:
    if nmpg is not None and b.get("mean") is not None:
        note = confidence_note(b)
        analysis = (
            f"{nmpg:.1f} nm/gal this flight. "
            f"Your average: {b['mean']:.1f} ± {b['std']:.1f} nm/gal "
            f"({b['n']} flights{note}, DA-stratified)."
        )
        insights = []
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = baseline_triggered(nmpg, b, rule)
                if triggered:
                    insights.append(text)
            elif rule["type"] == "trend":
                triggered, text = trend_triggered(b, rule)
                if triggered:
                    insights.append(text)
        return {"analysis": analysis, "insights": insights}
    if b.get("mean") is None:
        return {"analysis": "Still building your cruise efficiency baseline.", "insights": []}
    return {"analysis": "No cruise efficiency data for this flight.", "insights": []}


def cruise_fuel_flow(fuel_flow, b: dict, rule_triggers: list,
                      this_da=None, fleet_da_avg=None, fleet_da_std=None) -> dict:
    if fuel_flow is not None and b.get("mean") is not None:
        note = confidence_note(b)
        da_note = ""
        da_high = False
        if this_da is not None and fleet_da_avg is not None and fleet_da_std:
            da_z = (this_da - fleet_da_avg) / fleet_da_std
            da_note = f" at cruise DA {this_da:,.0f} ft (fleet avg {fleet_da_avg:,.0f} ft)"
            da_high = da_z > 1.0

        analysis = (
            f"{fuel_flow:.1f} gph this flight{da_note}. "
            f"Your average: {b['mean']:.1f} ± {b['std']:.1f} gph "
            f"({b['n']} flights{note}, all altitudes blended)."
        )
        insights = []
        for rule in rule_triggers:
            if rule["type"] == "baseline_deviation":
                triggered, text = baseline_triggered(fuel_flow, b, rule)
                if triggered:
                    if da_high:
                        insights.append(
                            text + " Note: this flight's cruise DA was "
                                   "significantly higher than your typical cruise — "
                                   "altitude and power setting affect fuel flow. "
                                   "A power/altitude model is needed for a fully valid comparison."
                        )
                    else:
                        insights.append(text)
        return {"analysis": analysis, "insights": insights}
    if b.get("mean") is None:
        return {"analysis": "Still building your cruise fuel flow baseline.", "insights": []}
    return {"analysis": "No cruise fuel flow data for this flight.", "insights": []}


def engine_ecu_inflight(ecu_runs: list[dict]) -> dict:
    """
    Returns {"analysis": str, "events": list[dict]}. `events` is
    analyze_inflight_pattern()'s per-event structure (cas.py) — the
    renderer reconstructs the per-event/per-alert detail lines from it.
    """
    inflight = [r for r in ecu_runs if r["classification"] == "IN_FLIGHT"]
    if not inflight:
        return {
            "analysis": "No IN-FLIGHT ENGINE ECU events — all occurrences are "
                        "expected FADEC behaviour (POWERUP, LANE_CHECK, SHUTDOWN).",
            "events": [],
        }
    pattern = analyze_inflight_pattern(inflight)
    return {
        "analysis": f"{len(inflight)} IN-FLIGHT ENGINE ECU event(s) detected "
                    f"— requires investigation.",
        "events": pattern["events"],
    }


def climb_thermal_rate(oil_rise, b: dict, rule_triggers: list) -> dict:
    if oil_rise is None or b.get("mean") is None:
        return {
            "analysis": "Insufficient climb data for thermal rate — "
                        "short or pattern-work flights don't contribute here.",
            "insights": [],
        }
    note = confidence_note(b)
    analysis = (
        f"Oil temp rose {oil_rise:.1f}°F/min during climb. "
        f"Your average: {b['mean']:.1f} ± {b['std']:.1f}°F/min "
        f"({b['n']} flights{note})."
    )
    insights = []
    for rule in rule_triggers:
        if rule["type"] == "baseline_deviation":
            triggered, text = baseline_triggered(oil_rise, b, rule)
            if triggered:
                insights.append(text)
    return {"analysis": analysis, "insights": insights}


def limit_exceedances(exceedances: list) -> dict:
    if exceedances:
        return {
            "analysis": f"{len(exceedances)} OM hard-limit exceedance(s) this flight:",
            "insights": [f"⚠ {exc}" for exc in exceedances],
        }
    return {"analysis": "No OM hard-limit exceedances this flight.", "insights": []}
