"""
Spec 09 v0.20 — phase-of-flight exclusion in filters (§7.5, Phase 8):
acceptance 25–28 on synthetic flights. (24, on the real log set, is in
tests/contract/test_phase_filter_real.py.)
"""
import copy

import pytest

from slingology_eis import workspace as ws
from slingology_eis.filters import (
    FILTER_PHASES, active_filters, classify_event, event_phases, evaluate_filter_health,
    preview_limit_filter, validate_filter, with_cas_targets,
)
from slingology_eis.limits import limit_catalog, load_engine_config
from slingology_eis.operations import FleetAnalysis, FlightAnalysis, evaluate_insights, update_fleet

from .test_limit_events import _exc
from .test_limit_filters import RULES, _filter, _fleet_of, _limit_topic

CFG = load_engine_config("916iS")
CAT = {lim["id"]: lim for lim in limit_catalog(CFG)}


def _idle(start_s, dur_s, observed=1700.0):
    return _exc("rpm_idle_min", "rpm", "Idle RPM minimum", start_s, dur_s, observed, 1800.0, limit_type="MIN", unit="rpm")


def _fp(start_s, dur_s, observed):
    return _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", start_s, dur_s, observed, 46.0)


def _segments(*spec):
    """("TAXI", 0, 100), ... -> phase segments [start_s, end_s)."""
    return [{"phase": p, "start_s": float(a), "end_s": float(b)} for p, a, b in spec]


def _flight(exceedances, phases, flight_id="f1", hours=10.0):
    return FlightAnalysis(
        flight_id=flight_id, analysis_key=flight_id, source_keys=[flight_id],
        header={"date": "2026-01-01", "start_utc": "2026-01-01T12:00:00", "engine_hours_start": hours, "engine_hours_end": hours + 0.9},
        phases=phases, metrics={}, exceedances=exceedances, provenance={}, limits=limit_catalog(CFG),
    )


def _events(iset, limit_id):
    return [e for i in _limit_topic(iset)["insights"] if i.get("limit_id") == limit_id for e in i.get("events", [])]


# ── Acceptance 25: the whole-event rule ──────────────────────────────────────

LANDING_TAXI = _segments(("APPROACH", 0, 100), ("LANDING_ROLL", 100, 200), ("TAXI", 200, 400))


def test_event_phases_follow_the_rows_in_order():
    assert event_phases(_idle(150, 100), LANDING_TAXI) == ["LANDING_ROLL", "TAXI"]          # rows 150..249
    assert event_phases(_idle(150, 50), LANDING_TAXI) == ["LANDING_ROLL"]                   # rows 150..199
    assert event_phases(_idle(350, 100), LANDING_TAXI) == ["TAXI", "UNKNOWN"]               # runs past the last segment
    assert event_phases({**_idle(0, 10), "elapsed_s": None}, LANDING_TAXI) == ["UNKNOWN"]
    assert event_phases(_idle(50, 60), _segments(("APPROACH", 0, 90), ("TAXI", 100, 200))) == ["APPROACH", "UNKNOWN", "TAXI"]


def test_acceptance_25_whole_event_rule():
    flt = _filter("rpm_idle_min", phases=["LANDING_ROLL", "TAXI"])
    lim = CAT["rpm_idle_min"]
    spanning = {**_idle(150, 100), "phases": event_phases(_idle(150, 100), LANDING_TAXI)}     # LANDING_ROLL -> TAXI
    assert classify_event(spanning, flt, lim) == "phase"

    only_landing = _filter("rpm_idle_min", phases=["LANDING_ROLL"])
    approach_to_landing = {**_idle(50, 100), "phases": event_phases(_idle(50, 100), LANDING_TAXI)}
    assert approach_to_landing["phases"] == ["APPROACH", "LANDING_ROLL"]
    assert classify_event(approach_to_landing, only_landing, lim) is None

    unknown = {**_idle(350, 100), "phases": event_phases(_idle(350, 100), LANDING_TAXI)}
    assert classify_event(unknown, flt, lim) is None

    # Through evaluate_insights: the suppressed event says which phases.
    fa = _flight([_idle(150, 100), _idle(50, 100)], LANDING_TAXI)
    evs = _events(evaluate_insights(fa, update_fleet([]), RULES, filters=[only_landing | {"phases": ["LANDING_ROLL", "TAXI"]}]), "rpm_idle_min")
    by_start = {e["elapsed_s"]: e for e in evs}
    assert by_start[150.0]["suppressed_by"] == "phase" and by_start[150.0]["phases"] == ["LANDING_ROLL", "TAXI"]
    assert by_start[50.0]["suppressed_by"] is None and by_start[50.0]["phases"] == ["APPROACH", "LANDING_ROLL"]


# ── Acceptance 26: combined intentions, precedence ───────────────────────────

GROUND_AIR = _segments(("WARMUP", 0, 300), ("CLIMB", 300, 600), ("CRUISE", 600, 5000))


def test_acceptance_26_magnitude_and_phase():
    flt = _filter("fuel_press_max", {"mode": "absolute", "value": 2.0}, note="", phases=["WARMUP"])
    in_warmup = _fp(100, 60, 50.0)          # +4 psi: beyond the band, but in an excluded phase
    in_cruise = _fp(1000, 60, 50.0)         # same event in a phase not excluded: a breach
    fa = _flight([in_warmup, in_cruise], GROUND_AIR)
    ins = _limit_topic(evaluate_insights(fa, update_fleet([]), RULES, filters=[flt]))["insights"]
    outcome = {i["filter"]["outcome"]: i for i in ins}
    assert [e["elapsed_s"] for e in outcome["breach"]["events"]] == [1000.0]
    assert [(e["elapsed_s"], e["suppressed_by"]) for e in outcome["suppressed"]["events"]] == [(100.0, "phase")]
    assert "within your filter (up to +2 psi or in WARMUP)" in outcome["suppressed"]["message"]["text"]

    # §11.3 precedence: phase > duration > magnitude.
    lim = CAT["fuel_press_max"]
    every = _filter("fuel_press_max", {"mode": "absolute", "value": 5.0}, {"max_event_s": 120}, phases=["WARMUP"])
    small_short_warm = {**_fp(100, 60, 47.0), "phases": ["WARMUP"]}
    small_short_cruise = {**_fp(1000, 60, 47.0), "phases": ["CRUISE"]}
    small_long_cruise = {**_fp(1000, 600, 47.0), "phases": ["CRUISE"]}
    assert classify_event(small_short_warm, every, lim) == "phase"
    assert classify_event(small_short_cruise, every, lim) == "duration"
    assert classify_event(small_long_cruise, every, lim) == "magnitude"


# ── Acceptance 27: monitoring ────────────────────────────────────────────────

def _monitor(peaks, phases):
    """One fuel_press_max event per flight at 100 s for 60 s, lying in
    `phases`' first segment; (fas, fleet)."""
    fas, peak_pts, pct_pts = [], [], []
    for i, peak in enumerate(peaks):
        fid = f"m{i:03d}"
        fas.append(_flight([_fp(100, 60, 46.0 + peak)], phases, flight_id=fid, hours=100.0 + i))
        base = {"flight_id": fid, "date": "2026-01-01", "x": 100.0 + i}
        peak_pts.append({**base, "value": peak})
        pct_pts.append({**base, "value": 20.0})
    fleet = FleetAnalysis(fleet_key="fk", flight_ids=[fa.flight_id for fa in fas],
                          metrics={"limit_fuel_press_max_peak_excess": {"points": peak_pts},
                                   "limit_fuel_press_max_time_above_pct": {"points": pct_pts}},
                          provenance={"baseline_config": {"outlier_z_threshold": 2.0}})
    return fas, fleet


def test_acceptance_27_excluded_phase_events_are_monitored_never_breached():
    typical = [1.0 + 0.1 * (i % 3) for i in range(12)]
    fas, fleet = _monitor(typical + [2.9, 2.9], _segments(("WARMUP", 0, 300)))
    flt = _filter("fuel_press_max", phases=["WARMUP"], reference=[f"m{i:03d}" for i in range(12)],
                  created_engine_hours=112.0)
    h = evaluate_filter_health(fas, fleet, [flt], CFG)[0]
    assert h["valid"] is True
    assert h["status"] == "drifting"                       # growth in excluded-phase events drives Drifting
    assert all(s["breaches"] == 0 for s in h["series"])    # a phase-suppressed event is never a breach
    assert [s["suppressed_by_phase"] for s in h["series"]] == [1] * 14

    # The same events outside the excluded phase are breaches.
    fas_air, fleet_air = _monitor(typical + [2.9, 2.9], _segments(("CRUISE", 0, 300)))
    h_air = evaluate_filter_health(fas_air, fleet_air, [flt], CFG)[0]
    assert all(s["suppressed_by_phase"] == 0 for s in h_air["series"])
    assert sum(s["breaches"] for s in h_air["series"]) == 14


# ── Acceptance 28: validation and storage ────────────────────────────────────

LIMITS = with_cas_targets({lim["id"]: lim for lim in CAT.values()})


@pytest.mark.parametrize("flt,code", [
    (_filter("rpm_idle_min", phases=["TAXI", "HOVER"]), "FILTER_PHASE_INVALID"),
    (_filter("rpm_idle_min", phases=["UNKNOWN"]), "FILTER_PHASE_INVALID"),
    (_filter("rpm_idle_min", phases=["TAXI", "TAXI"]), "FILTER_PHASE_INVALID"),
    (_filter("rpm_takeoff_max", {"mode": "absolute", "value": 10}, note="x", phases=["TAKEOFF_ROLL"]), "FILTER_NOT_ALLOWED"),
    (_filter("overboost", {"mode": "absolute", "value": 10}, note="x", phases=["CLIMB"]), "FILTER_NOT_ALLOWED"),
    ({"id": "c", "target": {"kind": "cas", "cas_id": "ENGINE ECU"}, "duration": {"max_event_s": 10}, "phases": ["TAXI"],
      "note": "", "reference": {"flight_ids": []}, "history": []}, "FILTER_NOT_ALLOWED"),
])
def test_acceptance_28_invalid_phase_conditions_leave_the_target_unfiltered(flt, code):
    assert code in [d["code"] for d in validate_filter(flt, LIMITS)]
    valid, diags = active_filters([flt], {lim["id"]: lim for lim in CAT.values()})
    assert valid == {} and code in [d["code"] for d in diags]


def test_acceptance_28_phase_only_filter_is_valid_and_all_phases_is_allowed():
    assert validate_filter(_filter("rpm_idle_min", phases=["TAXI", "LANDING_ROLL"]), LIMITS) == []
    assert validate_filter(_filter("rpm_idle_min", phases=list(FILTER_PHASES)), LIMITS) == []   # Q11: allowed
    assert [d["code"] for d in validate_filter(_filter("rpm_idle_min", phases=[]), LIMITS)] == ["FILTER_NOT_ALLOWED"]


def test_acceptance_28_storage(tmp_path):
    """A filters.json written before v0.20 loads unchanged; editing phases
    is an edit (reference reset, history entry); a phases-only filter saves."""
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    old = ws.save_filter(ws_dir, {"limit_id": "fuel_press_max", "magnitude": {"mode": "absolute", "value": 1.5}, "note": "x"},
                         reference_flight_ids=["a"])
    loaded = ws.load_filters(ws_dir)["filters"][0]
    assert "phases" not in loaded and loaded["magnitude"] == old["magnitude"]

    assert ws.filter_conditions_changed(loaded, {**loaded, "phases": ["WARMUP"]})
    edited = ws.save_filter(ws_dir, {**loaded, "phases": ["WARMUP"]}, reference_flight_ids=["b"])
    assert edited["phases"] == ["WARMUP"] and edited["reference"]["flight_ids"] == ["b"]
    assert edited["history"][-1]["action"] == "edited" and edited["history"][-1]["after"]["phases"] == ["WARMUP"]

    only = ws.save_filter(ws_dir, {"limit_id": "rpm_idle_min", "phases": ["TAXI"], "note": ""})
    assert only["phases"] == ["TAXI"] and "magnitude" not in only and "duration" not in only


def test_acceptance_28_without_phase_filters_insights_unchanged_apart_from_event_phases():
    """The v0.20 code path with no phase condition: same insights, same
    suppression, as the v0.19 classification order would give — the only
    addition is each event's `phases`."""
    fa = _flight([_fp(100, 40, 46.4), _fp(900, 60, 47.2), _fp(3000, 1980, 50.4)], GROUND_AIR)
    flt = _filter("fuel_press_max", {"mode": "absolute", "value": 2.5}, note="sender reads high")
    ins = _limit_topic(evaluate_insights(fa, update_fleet([]), RULES, filters=[flt]))["insights"]
    stripped = copy.deepcopy(ins)
    for i in stripped:
        for e in i.get("events", []):
            assert e.pop("phases")
    assert [[e["suppressed_by"] for e in i["events"]] for i in stripped] == [[None], ["magnitude", "magnitude"]]


def test_preview_breaks_suppression_down_by_phase():
    fas = [
        _flight([_idle(150, 100), _idle(50, 100)], LANDING_TAXI, flight_id="p1"),
        _flight([_idle(250, 60)], LANDING_TAXI, flight_id="p2"),
    ]
    fleet = _fleet_of(fas)
    draft = _filter("rpm_idle_min", phases=["LANDING_ROLL", "TAXI"])
    p = preview_limit_filter(fas, fleet, RULES, [], draft)["phases"]
    assert p["suppressed_by_phase"] == {"TAXI": {"events": 2, "flights": 2}, "LANDING_ROLL": {"events": 1, "flights": 1}}
    assert p["visible_events"] == 1 and p["visible_by_phase"] == {"LANDING_ROLL": 1, "APPROACH": 1}
    assert p["excludes_every_phase"] is False
    assert preview_limit_filter(fas, fleet, RULES, [], _filter("rpm_idle_min", phases=list(FILTER_PHASES)))["phases"]["excludes_every_phase"]
