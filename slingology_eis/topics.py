"""
topics.py — per-flight topic analysis and insight evaluation.

Each topic function is a pure computation: given a flight's own values
plus its personal baseline/rules, it returns the report's two-layer
content — {"analysis": str, "insights": list[dict]} — with no printing.
Each insight dict is {"trigger": "threshold"|"baseline_deviation"|"trend",
"text": str}; the trigger tag is what lets evaluate_insights()
(slingology_eis.operations) attribute each insight to a rule and
severity without re-deriving which check fired. notebooks/04_flight_
report.py is a thin renderer over these (it only reads ["text"]).

This mirrors Spec 01 §8.5's TopicResult/Insight shape at the level Stage
3 needs; the full typed contract (message templates, evidence refs) is
built in evaluate_insights(), not here — Spec 01 Q3 leaves the eventual
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
    t = b.get("trend") or {}
    r2, n, direction = t.get("r_squared"), t.get("n"), t.get("direction")
    # r2/n are None (and direction reads "insufficient data" / "insufficient_data"
    # / "flat / no clear trend" depending on which code path built this dict —
    # legacy fleet.py vs the Stage 3 contract) whenever there isn't enough data
    # for a fit; guard on the values themselves, not a specific spelling.
    if not t or r2 is None or n is None:
        return False, ""
    if r2 < rule.get("r2_min", 0.5) or n < rule.get("n_min", 10):
        return False, ""
    wanted = rule.get("direction")
    # "either" (Spec 08 §6): a drift in both directions matters, e.g. a
    # cylinder running hotter (lean injector) or cooler (ignition, probe).
    if direction == wanted or (wanted == "either" and direction in ("increasing", "decreasing")):
        return True, (f"⚠ Trending {direction} over engine hours "
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
                    insights.append({"trigger": "baseline_deviation", "text": text})
            elif rule["type"] == "trend":
                triggered, text = trend_triggered(b, rule)
                if triggered:
                    insights.append({"trigger": "trend", "text": text})
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
                insights.append({"trigger": "baseline_deviation", "text": text})
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
    insights = [{
        "trigger": "threshold",
        "text": "⚠ Rank instability is unusual for this engine — possible early "
                "injector or ignition imbalance. Compare per-cylinder EGT means "
                "in script 01.",
    }]
    return {"analysis": analysis, "insights": insights}


def hot_cylinder_change(
    window: list[dict],
    established: dict,
    rule: Optional[dict],
    engine_name: Optional[str] = None,
) -> dict:
    """
    Spec 08 §6 `cylinder_rank` topic. `window` is this flight's hottest-
    cylinder point preceded by up to `consecutive_flights - 1` earlier ones
    (oldest first, each {"hottest_cyl", "margin_f"}); `established` is
    baselines.established_hot_cylinder()'s result, computed without the
    flights in the window. `rule` is the hot_cyl_changed trigger, or None
    when the rule is disabled.

    Insights carry their own "severity" when it differs from the rule's —
    a mismatch against a profile prior (not yet learned for this aircraft)
    is informational, not a warning.
    """
    if not window:
        return {"analysis": "Insufficient cruise data for cylinder rank analysis.", "insights": []}
    this = window[-1]
    cyl, margin = this["hottest_cyl"], this.get("margin_f")
    margin_min = (rule or {}).get("margin_min_f", 15)
    margin_str = f"+{margin:.0f}°F over next" if margin is not None else "margin unknown"
    ambiguous = margin is None or margin < margin_min
    too_close = " — too close to call" if ambiguous else ""
    analysis = f"Hottest this flight: Cyl {cyl} ({margin_str}{too_close}). "

    src, usual = established.get("source"), established.get("cyl")
    if src == "learned":
        analysis += (f"Usual hottest for this aircraft: Cyl {usual} "
                     f"({established['share'] * 100:.0f}% of {established['n']} flights).")
    elif src == "prior":
        analysis += (f"Typical hottest for the {engine_name or 'engine'} profile: Cyl {usual} "
                     f"(not yet learned for this aircraft — {established['n']} usable flights).")
    else:
        analysis += "Usual hottest cylinder not yet established for this aircraft."

    insights = []
    if rule is None or src == "none":
        return {"analysis": analysis, "insights": insights}
    consecutive = max(1, int(rule.get("consecutive_flights", 2)))
    if len(window) < consecutive:
        return {"analysis": analysis, "insights": insights}
    changed = all(
        p["hottest_cyl"] != usual and p.get("margin_f") is not None and p["margin_f"] >= margin_min
        for p in window[-consecutive:]
    )
    if not changed:
        return {"analysis": analysis, "insights": insights}

    flights = f"for {consecutive} consecutive flights" if consecutive > 1 else "this flight"
    if src == "learned":
        text = (f"⚠ Cyl {cyl} ran hottest ({margin_str}) {flights}; this aircraft's usual "
                f"hottest is Cyl {usual}. A cylinder running hotter is consistent with a lean "
                f"injector; the usual hottest cooling can point to an ignition/plug issue or "
                f"an EGT probe fault. Compare the per-cylinder balance trend.")
        insights.append({"trigger": "threshold", "text": text})
    else:
        text = (f"Cyl {cyl} ran hottest ({margin_str}) {flights}; the typical "
                f"{engine_name or 'engine'} pattern is Cyl {usual}. Not an anomaly by itself — "
                f"this aircraft's own pattern isn't established yet.")
        insights.append({"trigger": "threshold", "text": text, "severity": "info"})
    return {"analysis": analysis, "insights": insights}


def cyl_deviation(cyls: list[dict]) -> dict:
    """
    Spec 08 §6 `egt_cyl_deviation` topic: each cylinder's cruise EGT vs.
    the mean of the others, against its own baseline. `cyls` holds one
    {"cyl", "value", "b", "triggers"} per cylinder (b: the topic-baseline
    shape baseline_triggered/trend_triggered read; triggers: the rule's
    triggers as they apply to that cylinder). Insights carry a
    "cyl" key so the caller can attach per-cylinder evidence.
    """
    present = [c for c in cyls if c["value"] is not None]
    if not present:
        return {"analysis": "Per-cylinder EGT balance not available.", "insights": []}
    parts = []
    for c in present:
        b = c["b"]
        avg = f" (avg {b['mean']:+.0f})" if b.get("mean") is not None else ""
        parts.append(f"Cyl {c['cyl']} {c['value']:+.0f}°F{avg}")
    n = max((c["b"].get("n") or 0) for c in present)
    analysis = "Vs. mean of the other cylinders: " + ", ".join(parts) + f" ({n} flights{confidence_note({'n': n})})."

    insights = []
    for c in present:
        for rule in c["triggers"]:
            if rule["type"] == "baseline_deviation":
                triggered, text = baseline_triggered(c["value"], c["b"], rule)
                if triggered:
                    insights.append({"trigger": "baseline_deviation", "cyl": c["cyl"],
                                     "text": f"Cyl {c['cyl']}: {text}"})
            elif rule["type"] == "trend":
                triggered, text = trend_triggered(c["b"], rule)
                if triggered:
                    insights.append({"trigger": "trend", "cyl": c["cyl"],
                                     "text": f"Cyl {c['cyl']}: {text}"})
    return {"analysis": analysis, "insights": insights}


def overboost(ob_total, ob_max, ob_limit, ob_exceeded: bool) -> dict:
    if ob_max is None:
        return {"analysis": "Overboost data not available (no RPM channel).", "insights": []}
    analysis = (
        f"Max continuous block: {ob_max}s. Total this flight: {ob_total}s. "
        f"OM limit: {ob_limit}s."
    )
    insights = []
    if ob_exceeded:
        insights.append({"trigger": "threshold", "text": f"⚠ Exceeded OM {ob_limit}s limit by {ob_max - ob_limit}s."})
    elif ob_max >= 240:
        insights.append({"trigger": "threshold", "text": f"⚠ Close call — {ob_limit - ob_max}s below the OM limit. "
                         f"Pull back to climb power promptly after takeoff."})
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
            insights.append({"trigger": "threshold", "text": (
                f"⚠ {abs(delta):.1f} inHg {direction} model — "
                f"{'possible turbo underperformance, monitor trend.' if delta < 0 else 'above model — verify sensor.'}"
            )})
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
            insights.append({"trigger": "threshold", "text": f"⚠ Exceeded OM limit of {rule['limit']}°F."})
        elif rule["type"] == "baseline_deviation":
            triggered, text = baseline_triggered(oil_max, b, rule)
            if triggered:
                insights.append({"trigger": "baseline_deviation", "text": text})
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
            insights.append({"trigger": "threshold", "text": f"⚠ Exceeded OM limit of {rule['limit']}°F."})
        elif rule["type"] == "baseline_deviation":
            triggered, text = baseline_triggered(coolant_max, b, rule)
            if triggered:
                insights.append({"trigger": "baseline_deviation", "text": text})
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
                insights.append({"trigger": "baseline_deviation", "text": text})
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
                    insights.append({"trigger": "baseline_deviation", "text": text})
            elif rule["type"] == "trend":
                triggered, text = trend_triggered(b, rule)
                if triggered:
                    insights.append({"trigger": "trend", "text": text})
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
                        text = (text + " Note: this flight's cruise DA was "
                                       "significantly higher than your typical cruise — "
                                       "altitude and power setting affect fuel flow. "
                                       "A power/altitude model is needed for a fully valid comparison.")
                    insights.append({"trigger": "baseline_deviation", "text": text})
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
                insights.append({"trigger": "baseline_deviation", "text": text})
    return {"analysis": analysis, "insights": insights}


def limit_exceedances(exceedances: list) -> dict:
    if exceedances:
        return {
            "analysis": f"{len(exceedances)} OM hard-limit exceedance(s) this flight:",
            "insights": [{"trigger": "threshold", "text": f"⚠ {exc}"} for exc in exceedances],
        }
    return {"analysis": "No OM hard-limit exceedances this flight.", "insights": []}
