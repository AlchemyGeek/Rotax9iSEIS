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

from .cas import ECU_CLASSES
from .fleet import confidence_label


# ── Shared rule-evaluation helpers (moved from notebook 04) ──────────────────

def z_score(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0
    return (value - mean) / std


def baseline_triggered(value, b: dict, rule: dict) -> tuple[bool, str, dict]:
    """
    Check a baseline_deviation trigger. Returns (triggered, insight_text,
    comparison). `comparison` (Spec 01 R8, §8.4 v0.13) names what the
    flight was actually compared against — {"scope": "band"|"all",
    "band": str|None, "n": int} — taken from b["comparison"] when present
    (operations.py's _topic_baseline sets it for every stratified or
    unstratified metric) or synthesized as an "all" comparison for a
    caller that built `b` some other way. The insight text always names
    the comparison too, not just the values field — a fallback from band
    to all-flights should be visible to the pilot reading it, not just
    to a client that happens to read `message.values`.
    """
    comparison = b.get("comparison") or {"scope": "all", "band": None, "n": b.get("n", 0)}
    if value is None or b.get("mean") is None or b.get("std") is None:
        return False, "", comparison
    z = z_score(value, b["mean"], b["std"])
    # Spec 14 §7.3 — the topic card shows a trigger's current value even
    # when it didn't fire ("not met: 1.2 std devs..."), so `z` is always
    # attached to `comparison` now, not only computed for the fired-text
    # branch below. Same number either way; this doesn't change whether
    # or what fires, only what's still available to read afterward.
    comparison = {**comparison, "z": z}
    threshold = rule.get("z_score_threshold", 2.0)
    if abs(z) >= threshold:
        direction = "above" if z > 0 else "below"
        if comparison.get("scope") == "band" and comparison.get("band"):
            scope_text = f"your other {comparison['band']} flights, n={comparison['n']}"
        else:
            scope_text = f"all your flights, n={comparison.get('n', 0)}"
        return True, f"{'⚠' if z > 0 else '↓'} {abs(z):.1f} std devs {direction} {scope_text}.", comparison
    return False, "", comparison


def trend_triggered(b: dict, rule: dict) -> tuple[bool, str, Optional[dict]]:
    """Check a trend trigger. Returns (triggered, insight_text, detail).
    `detail` (Spec 14 §7.3 — the topic card's "not met: R² 0.30 over 23
    flights" even when no insight fired) is {"r_squared", "n",
    "direction", "slope"} whenever a fit exists, None when there isn't
    enough data for one — same cases the insight text already
    distinguishes, just not discarded on the non-firing path anymore."""
    t = b.get("trend") or {}
    r2, n, direction = t.get("r_squared"), t.get("n"), t.get("direction")
    # r2/n are None (and direction reads "insufficient data" / "insufficient_data"
    # / "flat / no clear trend" depending on which code path built this dict —
    # legacy fleet.py vs the Stage 3 contract) whenever there isn't enough data
    # for a fit; guard on the values themselves, not a specific spelling.
    if not t or r2 is None or n is None:
        return False, "", None
    detail = {"r_squared": r2, "n": n, "direction": direction, "slope": t.get("slope")}
    if r2 < rule.get("r2_min", 0.5) or n < rule.get("n_min", 10):
        return False, "", detail
    wanted = rule.get("direction")
    # "either" (Spec 08 §6): a drift in both directions matters, e.g. a
    # cylinder running hotter (lean injector) or cooler (ignition, probe).
    if direction == wanted or (wanted == "either" and direction in ("increasing", "decreasing")):
        return True, (f"⚠ Trending {direction} over engine hours "
                      f"(slope={t['slope']:+.3f}/hr, R²={r2:.2f}, n={n})."), detail
    return False, "", detail


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
                triggered, text, comparison = baseline_triggered(spread, b, rule)
                if triggered:
                    insights.append({"trigger": "baseline_deviation", "text": text, "comparison": comparison})
            elif rule["type"] == "trend":
                triggered, text, _ = trend_triggered(b, rule)
                if triggered:
                    insights.append({"trigger": "trend", "text": text})
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
                triggered, text, comparison = baseline_triggered(c["value"], c["b"], rule)
                if triggered:
                    insights.append({"trigger": "baseline_deviation", "cyl": c["cyl"],
                                     "text": f"Cyl {c['cyl']}: {text}", "comparison": comparison})
            elif rule["type"] == "trend":
                triggered, text, _ = trend_triggered(c["b"], rule)
                if triggered:
                    insights.append({"trigger": "trend", "cyl": c["cyl"],
                                     "text": f"Cyl {c['cyl']}: {text}"})
    return {"analysis": analysis, "insights": insights}


def overboost(ob_total, ob_max, ob_limit, close_call_s: Optional[float] = None) -> dict:
    """
    Spec 09 v0.12 §10.3: a block past the limit is now an ordinary
    `limit_exceedances` event (§6.4) — this topic no longer reports it
    (no more `ob_exceeded`/filter suppression/breach here, all of that is
    generic to every limit now). What's left is the close call: a block
    under the limit but within `close_call_margin_s` of it is not an OM
    exceedance, so only this topic can report it. `close_call_s` is
    already shifted by any active filter band (the effective limit minus
    the margin), so the close call still moves with the band even though
    the exceedance itself no longer does anything special here.
    """
    if ob_max is None:
        return {"analysis": "Overboost data not available (no RPM channel).", "insights": []}
    analysis = (
        f"Max continuous block: {ob_max}s. Total this flight: {ob_total}s. "
        f"OM limit: {ob_limit}s."
    )
    insights = []
    if ob_max < ob_limit and ob_max >= (close_call_s if close_call_s is not None else ob_limit - 60):
        insights.append({"trigger": "threshold", "text": f"⚠ Close call — {ob_limit - ob_max}s below the OM limit. "
                         f"Pull back to climb power promptly after takeoff."})
    return {"analysis": analysis, "insights": insights}


def takeoff_map(obs_map, obs_pa, obs_oat, model_fit: dict, z: float = 2.0) -> dict:
    """
    Spec 10 D5: `model_fit` is this flight's own leave-one-out fit (the
    regression fitted on every OTHER flight — operations._leave_one_out_
    map_fit), not a fit that includes this flight. The tolerance is
    `z` times that fit's residual standard error, not a fixed inHg
    band. A flight whose pressure altitude or OAT falls outside the
    range the model was fitted on gets no insight — the comparison
    isn't meaningful there, so the analysis line says why instead.
    """
    if obs_map is None:
        return {
            "analysis": "No takeoff MAP data available — "
                        "flight may lack a TAKEOFF phase with RPM ≥ 5,500.",
            "insights": [],
        }
    n_model = model_fit.get("n", 0)
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

    pa_range = model_fit.get("pa_range")
    oat_range = model_fit.get("oat_range")
    outside_range = (
        (pa_range is not None and obs_pa is not None and not (pa_range[0] <= obs_pa <= pa_range[1]))
        or (oat_range is not None and obs_oat is not None and not (oat_range[0] <= obs_oat <= oat_range[1]))
    )
    if outside_range:
        analysis = (
            f"Observed MAP at takeoff: {obs_map:.1f} inHg at {pa_str}, {oat_str}. "
            f"This takeoff was outside the range of elevations or temperatures "
            f"your personal model has seen (n={n_model}), so it wasn't compared."
        )
        return {"analysis": analysis, "insights": insights}

    exp_map = predict_takeoff_map(model_fit, obs_pa, obs_oat) \
        if obs_pa is not None and obs_oat is not None else None
    r2 = model_fit.get("r_squared", 0)
    se = model_fit.get("residual_se")
    if exp_map is not None:
        delta = obs_map - exp_map
        conf = confidence_label(n_model).split(" ")[0]
        analysis = (
            f"Observed MAP at takeoff: {obs_map:.1f} inHg at {pa_str}, {oat_str}. "
            f"Model expected: {exp_map:.1f} inHg "
            f"(n={n_model}, {conf}, R²={r2:.2f})."
        )
        if se is not None and abs(delta) >= z * se:
            direction = "below" if delta < 0 else "above"
            tolerance = z * se
            reason = "possible turbo underperformance, monitor trend." if delta < 0 else "verify sensor."
            insights.append({"trigger": "threshold", "text": (
                f"⚠ {abs(delta):.2f} inHg {direction} model "
                f"(your takeoffs normally vary within ±{tolerance:.2f} inHg) — {reason}"
            )})
    else:
        analysis = (
            f"Observed MAP at takeoff: {obs_map:.1f} inHg. "
            f"Model available (n={n_model}) but PA/OAT missing for prediction."
        )
    return {"analysis": analysis, "insights": insights}


def _om_limit_text(om_limit: Optional[dict]) -> str:
    return f"{om_limit['limit_value']:.0f}°F" if om_limit else "248°F"


def oil_temp_peak(oil_max, b: dict, rule_triggers: list, om_limit: Optional[dict] = None,
                  limit_events: Optional[list] = None) -> dict:
    if oil_max is None or b.get("mean") is None:
        return {"analysis": "Oil temperature data not available.", "insights": []}
    note = confidence_note(b)
    analysis = (
        f"Peak {oil_max:.0f}°F. "
        f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
        f"({b['n']} flights{note}). OM limit: {_om_limit_text(om_limit)}."
    )
    # Spec 10 §4.1 (Spec 09 §10.2): no insight of its own for the limit —
    # TopicResult.limit_refs carries the reference, this just names it in
    # plain language when it fired (unsuppressed by any filter).
    if limit_events:
        analysis += f" Exceeded OM limit of {_om_limit_text(om_limit)} — see Operators Manual limits."
    insights = []
    for rule in rule_triggers:
        if rule["type"] == "baseline_deviation":
            triggered, text, comparison = baseline_triggered(oil_max, b, rule)
            if triggered:
                insights.append({"trigger": "baseline_deviation", "text": text, "comparison": comparison})
    return {"analysis": analysis, "insights": insights}


def coolant_temp_peak(coolant_max, b: dict, rule_triggers: list, om_limit: Optional[dict] = None,
                  limit_events: Optional[list] = None) -> dict:
    if coolant_max is None or b.get("mean") is None:
        return {"analysis": "Coolant temperature data not available.", "insights": []}
    note = confidence_note(b)
    analysis = (
        f"Peak {coolant_max:.0f}°F. "
        f"Your average: {b['mean']:.0f}°F ± {b['std']:.0f}°F "
        f"({b['n']} flights{note}). OM limit: {_om_limit_text(om_limit)}."
    )
    if limit_events:
        analysis += f" Exceeded OM limit of {_om_limit_text(om_limit)} — see Operators Manual limits."
    insights = []
    for rule in rule_triggers:
        if rule["type"] == "baseline_deviation":
            triggered, text, comparison = baseline_triggered(coolant_max, b, rule)
            if triggered:
                insights.append({"trigger": "baseline_deviation", "text": text, "comparison": comparison})
    return {"analysis": analysis, "insights": insights}


# How each ENGINE ECU class reads in the analysis line (Spec 01 §8.6).
_ECU_CLASS_PHRASE = {
    "GROUND_START": "at start",
    "LANE_CHECK": "in the lane check",
    "GROUND": "on the ground with the engine running",
    "IN_FLIGHT": "in flight",
    "GROUND_SHUTDOWN": "at shutdown",
}


_LANE_CHECK_SUMMARY = {"both": "both lanes ✓", "single": "one lane only", "none": "not detected"}


def engine_ecu_inflight(ecu_runs: list[dict], sub_threshold_blips: int = 0, lane_check: str = "none") -> dict:
    """
    Returns {"analysis": str} (Spec 01 §8.5 v0.21). The topic references
    its events rather than reporting them: GROUND and IN_FLIGHT runs are
    CAS events owned by limit_exceedances. The line counts this flight's
    runs by class, the sub-threshold blips, and the lane-check summary
    (informational — never an insight).
    """
    counts = {c: sum(1 for r in ecu_runs if r["classification"] == c) for c in ECU_CLASSES}
    parts = [f"{n} {_ECU_CLASS_PHRASE[c]}" for c, n in counts.items() if n]
    if sub_threshold_blips:
        parts.append(f"{sub_threshold_blips} brief blip{'s' if sub_threshold_blips != 1 else ''} not counted")
    analysis = ("ENGINE ECU: " + " · ".join(parts) + ".") if parts else "No ENGINE ECU alerts this flight."
    analysis += f" Lane check: {_LANE_CHECK_SUMMARY.get(lane_check, lane_check)}."
    return {"analysis": analysis}


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
            triggered, text, comparison = baseline_triggered(oil_rise, b, rule)
            if triggered:
                insights.append({"trigger": "baseline_deviation", "text": text, "comparison": comparison})
    return {"analysis": analysis, "insights": insights}


def _fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60} s" if s % 60 else f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60} min"


# Spec 01 §8.6 / Spec 03 §5.2 (v0.21): why a GROUND run isn't a lane
# check, in the pilot's words.
NOT_LANE_CHECK_PHRASE = {
    "rpm_below_band": "below the lane-check band",
    "rpm_above_band": "above the lane-check band",
    "too_long": "longer than a lane check",
    "moving": "while moving, so not a lane check",
}


def cas_event_phrase(e: dict) -> str:
    """One CAS event in words: "ENGINE ECU during TAXI, 7 s, 2,550 rpm —
    below the lane-check band" (Spec 09 §10.1, Spec 03 §5.2)."""
    cas_id = e.get("cas_id", "ENGINE ECU")
    if e["classification"] == "IN_FLIGHT":
        text = f"{cas_id} in flight ({e['phase']}), {e['duration_s']:.0f} s"
    else:
        text = f"{cas_id} during {e['phase']}, {e['duration_s']:.0f} s"
    rpm = (e.get("context") or {}).get("rpm")
    if rpm:
        text += f", {rpm:,.0f} rpm"
    reason = NOT_LANE_CHECK_PHRASE.get(e.get("not_lane_check_reason") or "")
    if reason:
        text += f" — {reason}"
    if e.get("phase_uncertain"):
        text += " (flight phase uncertain)"
    return text


def _cas_group_text(g: dict) -> str:
    events, kind = g["events"], g.get("kind", "exceedance")
    phrases = [cas_event_phrase(e) for e in events]
    if len(events) == 1:
        body = phrases[0]
    else:
        cas_id = g["limit"]["cas_id"]
        body = f"{cas_id}, {len(events)} events: " + "; ".join(p[len(cas_id) + 1:] for p in phrases)
    if kind == "filtered":
        return f"{body} — within your filter ({g.get('filter_text', '')})."
    if kind == "breach":
        return f"⚠ {body} — beyond your filter ({g.get('filter_text', '')})."
    return f"⚠ {body}."


def limit_exceedance_groups(groups: list[dict]) -> dict:
    """
    Spec 09 §10.1: one insight per limit per flight — or, for a filtered
    limit, a quiet "filtered" insight for the events the filter tolerates
    plus a "breach" insight for any it doesn't. `groups` holds one
    {"limit": {label, unit, limit_type, limit_value, severity}, "events":
    [serialized exceedance, ...], "kind": "exceedance"|"breach"|"filtered",
    "filter_text": str} per insight, in display order. Returns
    {"analysis", "insights"}; each insight carries its group index under
    "group" so the caller can attach limit_id, events and evidence.
    """
    if not groups:
        return {"analysis": "No OM hard-limit exceedances this flight.", "insights": []}
    insights = []
    total = suppressed = 0
    limits_seen = set()
    cas_events = 0
    for i, g in enumerate(groups):
        lim, events = g["limit"], g["events"]
        kind = g.get("kind", "exceedance")
        if lim.get("kind") == "cas":
            # Spec 09 v0.18 §10.1: a classified CAS alert's events.
            cas_events += len(events)
            if kind == "filtered":
                suppressed += len(events)
            insights.append({"trigger": "threshold", "text": _cas_group_text(g), "group": i})
            continue
        limits_seen.add(lim.get("id", lim["label"]))
        total += len(events)
        worst = max(events, key=lambda e: e.get("excess") if e.get("excess") is not None else
                    (e["observed_value"] if lim["limit_type"] == "MAX" else -e["observed_value"]))
        unit = lim.get("unit", "")
        # A duration-valued limit's own "value" IS a block length (Spec 09
        # §6.4) — duration_s is the whole block, not time spent past the
        # limit within it, so "past the limit" has to sum the excess
        # instead or it overstates the overage (a 389 s block past a 300 s
        # limit is 89 s over, not 389 s "past the limit").
        if unit == "s":
            time_above = sum(e.get("excess") or 0 for e in events)
        else:
            time_above = sum(e["duration_s"] for e in events)
        side = "min" if lim["limit_type"] == "MIN" else "max"
        count = f"{len(events)} event{'s' if len(events) != 1 else ''}"
        worst_text = f"worst {worst['observed_value']:.1f} {unit} ({side} {lim['limit_value']:.1f} {unit})"
        if kind == "filtered":
            suppressed += len(events)
            text = (f"{lim['label']}: {count} within your filter ({g.get('filter_text', '')}), "
                    f"{worst_text}, {_fmt_duration(time_above)} past the limit.")
        elif kind == "breach":
            text = (f"⚠ [{lim['severity']}] {lim['label']}: {count} beyond your filter "
                    f"({g.get('filter_text', '')}), {worst_text}, {_fmt_duration(time_above)} past the limit.")
        else:
            text = (f"⚠ [{lim['severity']}] {lim['label']}: {count}, {worst_text}, "
                    f"{_fmt_duration(time_above)} past the limit.")
        insights.append({"trigger": "threshold", "text": text, "group": i})
    n_limits = len(limits_seen)
    if n_limits:
        analysis = (f"{n_limits} OM limit{'s' if n_limits != 1 else ''} exceeded this flight "
                    f"({total} event{'s' if total != 1 else ''}"
                    + (f", {suppressed} within your filters" if suppressed else "") + "):")
        if cas_events:
            analysis = analysis[:-1] + f"; {cas_events} alert event{'s' if cas_events != 1 else ''}:"
    else:
        analysis = (f"No OM hard-limit exceedances this flight; {cas_events} alert "
                    f"event{'s' if cas_events != 1 else ''}"
                    + (f", {suppressed} within your filters" if suppressed else "") + ":")
    return {"analysis": analysis, "insights": insights}


def limit_exceedances(exceedances: list) -> dict:
    if exceedances:
        return {
            "analysis": f"{len(exceedances)} OM hard-limit exceedance(s) this flight:",
            "insights": [{"trigger": "threshold", "text": f"⚠ {exc}"} for exc in exceedances],
        }
    return {"analysis": "No OM hard-limit exceedances this flight.", "insights": []}
