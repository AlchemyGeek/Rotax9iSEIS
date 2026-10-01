"""
Spec 09 Phase 3: limit filters — policy, validation, suppression, the
filtered/breach insights, topic parity, overboost, preview and caching.
"""
import copy
import json
from pathlib import Path

import pytest

from slingology_eis import workspace as ws
from slingology_eis.filters import (
    band_text,
    classify_event,
    comparison_set,
    frozen_baseline,
    preview_limit_filter,
    propose_limit_filter,
    resolve_filter_policy,
    validate_filter,
    validate_limit_filter,
)
from slingology_eis.limits import limit_catalog, load_engine_config
from slingology_eis.operations import FleetAnalysis, _limit_insight_id, analyze_flight, evaluate_insights, update_fleet

from ..conftest import LOGS_DIR
from .test_limit_events import _exc, _flight, _oil_fleet, _oil_metric

CFG = load_engine_config("916iS")
CAT = {lim["id"]: lim for lim in limit_catalog(CFG)}
RULES = json.loads((Path(__file__).resolve().parents[2] / "insight_rules.json").read_text())


def _filter(limit_id, magnitude=None, duration=None, note="", fid="flt_1", reference=None, **kw):
    f = {"id": fid, "limit_id": limit_id, "note": note, "created_at": "2026-09-30T00:00:00Z",
         "reference": {"flight_ids": reference or []}, "history": [], **kw}
    if magnitude:
        f["magnitude"] = magnitude
    if duration:
        f["duration"] = duration
    return f


def _limit_topic(iset):
    return next(t for t in iset.topics if t["topic_id"] == "limit_exceedances")


def _fp(start_s, dur_s, observed):
    return _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", start_s, dur_s, observed, 46.0)


# ── Policy (§6.3) ─────────────────────────────────────────────────────────────

def test_caution_limits_allow_every_mode_without_caps():
    p = resolve_filter_policy(CAT["fuel_press_max"])
    assert p["filterable"] and p["magnitude_modes"] == ["absolute", "percent", "z"]
    assert p["max_band_abs"] is None and not p["note_required"] and p["review_interval_h"] == 50


def test_warning_limit_without_caps_is_not_filterable():
    lim = {k: v for k, v in CAT["oil_temp_max"].items() if k != "filter_policy"}
    p = resolve_filter_policy(lim)
    assert not p["filterable"] and "caps" in p["reason"]


def test_warning_limit_with_caps():
    p = resolve_filter_policy(CAT["oil_temp_max"])
    assert p["filterable"] and p["magnitude_modes"] == ["absolute", "percent"]
    assert p["note_required"] and p["review_interval_h"] == 25


def test_oil_pressure_minimum_is_never_filterable():
    for engine in ("912iS", "914iS", "915iS", "916iS"):
        lim = next(l for l in limit_catalog(load_engine_config(engine)) if l["id"] == "oil_press_min")
        assert not resolve_filter_policy(lim)["filterable"]


def test_overboost_has_no_duration_condition():
    p = resolve_filter_policy(CAT["overboost"])
    assert p["filterable"] and not p["duration_allowed"] and p["max_duration_s"] is None


# ── Guardrails (§7.3, acceptance 8) ───────────────────────────────────────────

@pytest.mark.parametrize("flt,code", [
    (_filter("oil_temp_max", {"mode": "z", "value": 2}, note="gauge"), "FILTER_NOT_ALLOWED"),
    (_filter("oil_temp_max", {"mode": "absolute", "value": 6}, note="gauge"), "FILTER_NOT_ALLOWED"),
    (_filter("oil_temp_max", {"mode": "percent", "value": 5}, note="gauge"), "FILTER_NOT_ALLOWED"),  # 12.4°F > 5
    (_filter("oil_temp_max", duration={"max_event_s": 30}, note="gauge"), "FILTER_NOT_ALLOWED"),
    (_filter("oil_temp_max", {"mode": "absolute", "value": 3}), "FILTER_NOTE_REQUIRED"),
    (_filter("oil_press_min", {"mode": "absolute", "value": 1}, note="x"), "FILTER_NOT_ALLOWED"),
    (_filter("no_such_limit", {"mode": "absolute", "value": 1}), "FILTER_UNKNOWN_LIMIT"),
    (_filter("fuel_press_max"), "FILTER_NOT_ALLOWED"),                               # no condition
    (_filter("fuel_press_max", {"mode": "absolute", "value": -1}), "FILTER_NOT_ALLOWED"),
    (_filter("overboost", duration={"max_event_s": 5}, note="x"), "FILTER_NOT_ALLOWED"),
    (_filter("fuel_press_max", {"mode": "z", "value": 2}), "FILTER_REFERENCE_LOW_N"),
])
def test_invalid_filters_are_diagnosed(flt, code):
    diags = validate_filter(flt, CAT, update_fleet([]))
    assert code in [d["code"] for d in diags]


def test_valid_filters_pass():
    assert validate_limit_filter(_filter("fuel_press_max", {"mode": "absolute", "value": 2.5}), CFG) == []
    assert validate_limit_filter(_filter("oil_temp_max", {"mode": "percent", "value": 2}, note="gauge"), CFG) == []


def test_invalid_filter_leaves_the_limit_unfiltered_even_if_hand_edited():
    fa = _flight([_exc("oil_temp_max", "oil_temp_f", "Oil temp maximum", 100, 30, 262.0, 248.0,
                       severity="WARNING", unit="°F")])
    hand_edited = _filter("oil_temp_max", {"mode": "absolute", "value": 50})   # over the 5°F cap, no note
    iset = evaluate_insights(fa, update_fleet([]), RULES, filters=[hand_edited])
    ins = _limit_topic(iset)["insights"]
    assert len(ins) == 1 and "filter" not in ins[0] and ins[0]["severity"] == "limit"
    codes = {d["code"] for d in iset.header_warnings}
    assert {"FILTER_NOT_ALLOWED", "FILTER_NOTE_REQUIRED"} <= codes


def test_only_the_newest_filter_for_a_limit_applies():
    old = _filter("fuel_press_max", {"mode": "absolute", "value": 0.1}, fid="a", created_at="2026-01-01")
    new = _filter("fuel_press_max", {"mode": "absolute", "value": 5}, fid="b", created_at="2026-02-01")
    fa = _flight([_fp(100, 40, 47.0)])
    iset = evaluate_insights(fa, update_fleet([]), RULES, filters=[old, new])
    ins = _limit_topic(iset)["insights"]
    assert [i["filter"]["filter_id"] for i in ins] == ["b"]
    assert any(d["code"] == "FILTER_MULTIPLE_FOR_LIMIT" for d in iset.header_warnings)


# ── Suppression (§7, acceptance 6-7) ──────────────────────────────────────────

def test_magnitude_filter_splits_into_filtered_and_breach():
    fa = _flight([_fp(100, 40, 46.4), _fp(900, 60, 47.2), _fp(3000, 1980, 50.4)])
    flt = _filter("fuel_press_max", {"mode": "absolute", "value": 2.5}, note="sender reads high")
    ins = _limit_topic(evaluate_insights(fa, update_fleet([]), RULES, filters=[flt]))["insights"]
    breach, filtered = ins
    assert breach["filter"] == {"filter_id": "flt_1", "outcome": "breach"}
    assert breach["severity"] == "limit" and "beyond your filter" in breach["message"]["text"]
    assert [e["observed_value"] for e in breach["events"]] == [50.4]
    assert filtered["filter"]["outcome"] == "suppressed" and filtered["severity"] == "info"
    assert [e["suppressed_by"] for e in filtered["events"]] == ["magnitude", "magnitude"]
    assert "2 events within your filter (up to +2.5 psi)" in filtered["message"]["text"]
    assert breach["id"] == _limit_insight_id("f1", "fuel_press_max", "breach")
    assert filtered["id"] == _limit_insight_id("f1", "fuel_press_max", "filtered")


def test_all_suppressed_is_one_quiet_insight():
    fa = _flight([_fp(100, 40, 46.4), _fp(900, 60, 47.2)])
    flt = _filter("fuel_press_max", {"mode": "percent", "value": 3})   # 3% of 46 = 1.38 psi
    ins = _limit_topic(evaluate_insights(fa, update_fleet([]), RULES, filters=[flt]))["insights"]
    assert len(ins) == 1 and ins[0]["severity"] == "info" and ins[0]["filter"]["outcome"] == "suppressed"
    assert "(3%)" in ins[0]["message"]["text"]


def test_filtered_warning_limit_is_watch():
    fa = _flight([_exc("oil_temp_max", "oil_temp_f", "Oil temp maximum", 100, 30, 250.0, 248.0,
                       severity="WARNING", unit="°F")])
    flt = _filter("oil_temp_max", {"mode": "absolute", "value": 3}, note="gauge reads high")
    ins = _limit_topic(evaluate_insights(fa, update_fleet([]), RULES, filters=[flt]))["insights"]
    assert [i["severity"] for i in ins] == ["watch"]


def test_either_filter_duration_or_magnitude():
    flt = _filter("fuel_press_max", {"mode": "absolute", "value": 1.0}, {"max_event_s": 30})
    lim = CAT["fuel_press_max"]
    assert classify_event(_fp(0, 20, 49.0), flt, lim) == "duration"     # beyond band, but short
    assert classify_event(_fp(0, 600, 46.5), flt, lim) == "magnitude"   # long, but within band
    assert classify_event(_fp(0, 600, 49.0), flt, lim) is None          # neither: breach


def test_min_limit_band_uses_excess():
    lim = CAT["fuel_press_min"]
    e = _exc("fuel_press_min", "fuel_press_psi", "Fuel pressure minimum", 0, 30, 41.5, 42.0, "MIN", "WARNING")
    flt = _filter("fuel_press_min", {"mode": "absolute", "value": 1.0}, note="x")
    assert classify_event(e, flt, lim) == "magnitude"
    assert band_text(flt, lim) == "up to -1 psi"


# ── Topic parity (§10.2, acceptance 5) ────────────────────────────────────────

def _hot_oil_flight(observed):
    return _flight([_exc("oil_temp_max", "oil_temp_f", "Oil temp maximum", 100, 30, observed, 248.0,
                         severity="WARNING", unit="°F")], metrics=_oil_metric(observed))


def test_filter_on_oil_temp_hides_the_topic_threshold_but_not_baseline_deviation():
    flt = _filter("oil_temp_max", {"mode": "absolute", "value": 5}, note="gauge reads high")
    fa = _hot_oil_flight(251.0)   # z vs the 200-211°F fleet: baseline_deviation fires
    before = next(t for t in evaluate_insights(fa, _oil_fleet(), RULES).topics if t["topic_id"] == "oil_temp_peak")
    after = next(t for t in evaluate_insights(fa, _oil_fleet(), RULES, filters=[flt]).topics
                 if t["topic_id"] == "oil_temp_peak")
    assert sorted(i["trigger"] for i in before["insights"]) == ["baseline_deviation", "threshold"]
    assert [i["trigger"] for i in after["insights"]] == ["baseline_deviation"]


def test_breach_still_fires_the_topic_threshold():
    flt = _filter("oil_temp_max", {"mode": "absolute", "value": 5}, note="gauge reads high")
    fa = _hot_oil_flight(260.0)
    t = next(t for t in evaluate_insights(fa, _oil_fleet(), RULES, filters=[flt]).topics if t["topic_id"] == "oil_temp_peak")
    assert "threshold" in [i["trigger"] for i in t["insights"]]


# ── Overboost (§6.4, §10.3, acceptance 9) ─────────────────────────────────────

def _ob_flight(ob_max):
    return _flight([], metrics={"overboost_max_block_s": {"id": "overboost_max_block_s", "value": ob_max},
                                "overboost_total_s": {"id": "overboost_total_s", "value": ob_max}})


@pytest.mark.parametrize("ob_max,expected", [
    (250, None),                    # close call now starts at 300 + 20 - 60 = 260 s
    (270, ("Close call", None)),
    (310, ("within your filter", "suppressed")),
    (330, ("beyond your filter", "breach")),
])
def test_overboost_band_shifts_limit_and_close_call(ob_max, expected):
    flt = _filter("overboost", {"mode": "absolute", "value": 20}, note="normal climb procedure")
    ins = next(t for t in evaluate_insights(_ob_flight(ob_max), update_fleet([]), RULES, filters=[flt]).topics
               if t["topic_id"] == "overboost_time")["insights"]
    if expected is None:
        assert ins == []
        return
    text, outcome = expected
    assert len(ins) == 1 and text in ins[0]["message"]["text"]
    assert (ins[0].get("filter") or {}).get("outcome") == outcome
    if outcome == "suppressed":
        assert ins[0]["severity"] == "watch"


# ── z mode and the frozen baseline (§7.1, §8.1) ───────────────────────────────

def _z_fleet(values, bands=None):
    points = [{"flight_id": f"r{i}", "date": "2026-01-01", "x": float(i), "value": v,
               **({"band": bands[i]} if bands else {})} for i, v in enumerate(values)]
    return FleetAnalysis(fleet_key="fk", flight_ids=[p["flight_id"] for p in points],
                         metrics={"limit_fuel_press_max_peak_excess": {"points": points}},
                         provenance={"baseline_config": {}})


def test_frozen_baseline_is_the_baseline_of_the_reference_points():
    fleet = _z_fleet([0.2, 0.4, 0.3, 0.5, 9.0])
    fb = frozen_baseline(fleet, "limit_fuel_press_max_peak_excess", ["r0", "r1", "r2", "r3"])
    assert fb["n"] == 4 and fb["mean"] == pytest.approx(0.35)
    # a reference flight later excluded is absent from the fleet's points
    fleet.metrics["limit_fuel_press_max_peak_excess"]["points"].pop(0)
    assert frozen_baseline(fleet, "limit_fuel_press_max_peak_excess", ["r0", "r1", "r2", "r3"])["n"] == 3


def test_z_filter_uses_frozen_reference_and_std_floor():
    fleet = _z_fleet([0.3] * 12)          # std 0 -> floored to 5% of 46 = 2.3 psi
    ids = [f"r{i}" for i in range(12)]
    flt = _filter("fuel_press_max", {"mode": "z", "value": 2}, reference=ids)
    assert validate_filter(flt, CAT, fleet) == []
    fa = _flight([_fp(0, 60, 46.3 + 4.0), _fp(900, 60, 46.3 + 5.0)])   # z = 4.0/2.3 = 1.7, 5.0/2.3 = 2.2
    ins = _limit_topic(evaluate_insights(fa, fleet, RULES, filters=[flt]))["insights"]
    outcomes = {i["filter"]["outcome"]: [e["observed_value"] for e in i["events"]] for i in ins}
    assert outcomes == {"breach": [51.3], "suppressed": [50.3]}


def test_z_reference_below_n_min_makes_the_filter_invalid():
    fleet = _z_fleet([0.3] * 9)
    flt = _filter("fuel_press_max", {"mode": "z", "value": 2}, reference=[f"r{i}" for i in range(9)])
    assert [d["code"] for d in validate_filter(flt, CAT, fleet)] == ["FILTER_REFERENCE_LOW_N"]


def test_comparison_set_uses_the_band_only_with_enough_points():
    fleet = _z_fleet([0.3] * 10 + [2.0] * 5, bands=["mild"] * 10 + ["cold"] * 5)
    fb = frozen_baseline(fleet, "limit_fuel_press_max_peak_excess", [f"r{i}" for i in range(15)])
    stats, cmp = comparison_set(fb, "mild")
    assert cmp == {"scope": "band", "band": "mild", "n": 10} and stats["mean"] == pytest.approx(0.3)
    _, cmp = comparison_set(fb, "cold")
    assert cmp["scope"] == "all" and cmp["n"] == 15


# ── Caching (acceptance 14) and notes ─────────────────────────────────────────

def test_filters_change_filters_hash_not_analysis_or_fleet_key():
    fa, fleet = _flight([_fp(100, 40, 46.4)]), update_fleet([])
    a = evaluate_insights(fa, fleet, RULES)
    b = evaluate_insights(fa, fleet, RULES, filters=[_filter("fuel_press_max", {"mode": "absolute", "value": 1})])
    c = evaluate_insights(fa, fleet, RULES, filters=[_filter("fuel_press_max", {"mode": "absolute", "value": 2})])
    assert len({a.filters_hash, b.filters_hash, c.filters_hash}) == 3
    assert a.analysis_key == b.analysis_key and a.fleet_key == b.fleet_key


def test_note_saved_before_filtering_stays_visible():
    fa = _flight([_fp(100, 40, 46.4)])
    note = [{"ref": {"kind": "insight", "insight_id": _limit_insight_id("f1", "fuel_press_max", "exceedance")},
             "note": "sender reads high"}]
    flt = _filter("fuel_press_max", {"mode": "absolute", "value": 1})
    ins = _limit_topic(evaluate_insights(fa, update_fleet([]), RULES, annotations=note, filters=[flt]))["insights"]
    assert ins[0]["note"] == "sender reads high"


# ── Preview (acceptance 13) ───────────────────────────────────────────────────

def _fleet_of(fas):
    return FleetAnalysis(fleet_key="fk", flight_ids=[fa.flight_id for fa in fas], metrics={},
                         provenance={"baseline_config": {}})


def test_preview_counts_match_the_saved_filter():
    fas = [_flight([_fp(100, 40, 46.4), _fp(900, 60, 50.4)], flight_id="a"),
           _flight([_fp(100, 40, 47.0)], flight_id="b"),
           _flight([], flight_id="c")]
    fleet = _fleet_of(fas)
    draft = _filter("fuel_press_max", {"mode": "absolute", "value": 2.5}, fid=None)
    p = preview_limit_filter(fas, fleet, RULES, [], draft)
    assert p["valid"] and p["events_total"] == 3 and p["events_hidden"] == 2
    assert p["flights_affected"] == 2 and p["flights_with_breach"] == 1
    saved = {**draft, "id": "flt_saved"}
    suppressed = sum(1 for fa in fas for i in _limit_topic(evaluate_insights(fa, fleet, RULES, filters=[saved]))["insights"]
                     for e in i["events"] if e["suppressed_by"])
    assert suppressed == p["events_hidden"]


def test_preview_replaces_an_existing_filter_on_the_same_limit():
    fas = [_flight([_fp(100, 40, 46.4), _fp(900, 60, 47.0)], flight_id="a")]
    existing = _filter("fuel_press_max", {"mode": "absolute", "value": 0.5}, fid="old")
    draft = _filter("fuel_press_max", {"mode": "absolute", "value": 2.0}, fid="old")
    p = preview_limit_filter(fas, _fleet_of(fas), RULES, [existing], draft)
    assert p["events_hidden"] == 1   # the 47.0 event, newly within the wider band


# ── Real data: KACV (acceptance 6) ────────────────────────────────────────────

_KACV = LOGS_DIR / "log_20260423_200615_KACV.csv"


@pytest.mark.skipif(not _KACV.exists(), reason="needs the private KACV log")
def test_kacv_fuel_pressure_filter():
    fa = analyze_flight(_KACV.read_bytes(), _KACV.name, CFG, "916iS")
    flt = _filter("fuel_press_max", {"mode": "absolute", "value": 2.5}, note="sender reads high")
    ins = [i for i in _limit_topic(evaluate_insights(fa, update_fleet([]), RULES, filters=[flt]))["insights"]
           if i["limit_id"] == "fuel_press_max"]
    assert [i["filter"]["outcome"] for i in ins] == ["breach", "suppressed"]
    assert [e["observed_value"] for e in ins[0]["events"]] == [50.4]
    assert len(ins[1]["events"]) == len([e for e in fa.exceedances if e["limit_id"] == "fuel_press_max"]) - 1


# ── Storage (§9) ──────────────────────────────────────────────────────────────

def test_filter_store_create_edit_delete(tmp_path):
    f = ws.save_filter(tmp_path, {"limit_id": "fuel_press_max", "magnitude": {"mode": "absolute", "value": 2.5},
                                  "note": "sender"}, reference_flight_ids=["a", "b"], engine_hours=120.5)
    assert f["id"].startswith("flt") and f["reference"]["flight_ids"] == ["a", "b"]
    assert [h["action"] for h in f["history"]] == ["created"] and f["created_engine_hours"] == 120.5

    same = ws.save_filter(tmp_path, {**f, "note": "sender"})
    assert same["history"] == f["history"]          # no-op edit leaves no history

    edited = {"id": f["id"], "limit_id": "fuel_press_max", "duration": {"max_event_s": 20}, "note": "sender"}
    assert ws.filter_conditions_changed(f, edited)
    e = ws.save_filter(tmp_path, edited, reference_flight_ids=["c"])
    assert "magnitude" not in e and e["duration"] == {"max_event_s": 20}
    assert e["reference"]["flight_ids"] == ["c"] and e["history"][-1]["action"] == "edited"
    assert e["history"][-1]["before"]["magnitude"] == {"mode": "absolute", "value": 2.5}

    assert ws.delete_filter(tmp_path, f["id"]) and ws.load_filters(tmp_path)["filters"] == []
    assert not ws.delete_filter(tmp_path, f["id"])


# ── Change monitor (§8, Phase 4) ──────────────────────────────────────────────

from slingology_eis.filters import effective_reference, evaluate_filter_health  # noqa: E402
from slingology_eis.operations import FlightAnalysis  # noqa: E402


def _monitor_fixture(rows):
    """rows: one (peak_excess | None, time_above_pct, band | None) per flight,
    oldest first, 1 engine hour apart. Returns (fas, fleet)."""
    fas, peak_pts, pct_pts = [], [], []
    for i, (peak, pct, band) in enumerate(rows):
        fid = f"m{i:03d}"
        excs = [] if peak is None else [_exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum",
                                             100, 60, 46.0 + peak, 46.0)]
        metrics = {"oat_band": {"id": "oat_band", "value": band}}
        fas.append(FlightAnalysis(flight_id=fid, analysis_key=fid, source_keys=[fid],
                                  header={"date": f"2026-01-01", "start_utc": "x",
                                          "engine_hours_start": 100.0 + i, "engine_hours_end": 100.9 + i},
                                  metrics=metrics, exceedances=excs, provenance={}, limits=list(CAT.values())))
        base = {"flight_id": fid, "date": "2026-01-01", "x": 100.0 + i, **({"band": band} if band else {})}
        if peak is not None:
            peak_pts.append({**base, "value": peak})
        pct_pts.append({**base, "value": pct})
    fleet = FleetAnalysis(fleet_key="fk", flight_ids=[fa.flight_id for fa in fas],
                          metrics={"limit_fuel_press_max_peak_excess": {"points": peak_pts},
                                   "limit_fuel_press_max_time_above_pct": {"points": pct_pts}},
                          provenance={"baseline_config": {"outlier_z_threshold": 2.0}})
    return fas, fleet


def _health(rows, n_ref, **flt_kw):
    fas, fleet = _monitor_fixture(rows)
    flt_kw.setdefault("created_engine_hours", 100.0 + n_ref)
    flt = _filter("fuel_press_max", flt_kw.pop("magnitude", {"mode": "absolute", "value": 3.0}),
                  reference=[f"m{i:03d}" for i in range(n_ref)], **flt_kw)
    return evaluate_filter_health(fas, fleet, [flt], CFG)[0]


_TYPICAL = [(1.0 + 0.1 * (i % 3), 20.0 + (i % 3), None) for i in range(12)]


def test_monitor_stable():
    h = _health(_TYPICAL + [(1.1, 21.0, None)] * 3, 12)
    assert h["status"] == "stable" and h["reasons"] == []
    assert sum(s["monitored"] for s in h["series"]) == 3
    assert h["frozen_baseline"]["peak_excess"]["n"] == 12


def test_monitor_breached_then_reviewed():
    rows = _TYPICAL + [(1.1, 21.0, None), (4.0, 21.0, None), (1.1, 21.0, None)]
    h = _health(rows, 12)
    assert h["status"] == "breached" and h["last_breach"]["flight_id"] == "m013"
    reviewed = _health(rows, 12, reviewed_engine_hours=114.5)
    assert reviewed["status"] == "stable"


def test_monitor_drift_needs_two_consecutive_flights():
    # the 2.3 psi floor (5% of 46) dominates the tiny reference std: z = (x - 1.1) / 2.3
    one = _health(_TYPICAL + [(1.1, 21.0, None), (2.9, 21.0, None)], 12)
    two = _health(_TYPICAL + [(2.9, 21.0, None), (2.9, 21.0, None)], 12)
    assert one["status"] == "stable"
    assert two["status"] == "stable"      # z = 0.8: within the floor
    drift = _health(_TYPICAL + [(1.0, 60.0, None), (1.0, 60.0, None)], 12)
    assert drift["status"] == "drifting"
    assert drift["reasons"][0] == ("Fuel pressure maximum spent more of the flight past the limit than usual on your "
                                   "last 2 flights: 60% and 60% of engine time, against a typical 21% for all your "
                                   "reference flights (12 flights).")
    assert drift["drift_details"][0]["comparison"] == {"scope": "all", "band": None, "n": 12}
    single = _health(_TYPICAL + [(1.0, 21.0, None), (1.0, 60.0, None)], 12)
    assert single["status"] == "stable"


def test_monitor_drift_threshold_is_the_metrics_outlier_z():
    """Acceptance 11: the per-limit metric's outlier_z_threshold override
    decides drift too. Reference time above: 21 ± 0.85 %, floored to 1."""
    fas, fleet = _monitor_fixture(_TYPICAL + [(1.0, 24.0, None), (1.0, 24.0, None)])   # z = 3
    flt = _filter("fuel_press_max", {"mode": "absolute", "value": 3.0},
                  reference=[f"m{i:03d}" for i in range(12)], created_engine_hours=112.0)
    assert evaluate_filter_health(fas, fleet, [flt], CFG)[0]["status"] == "drifting"
    fleet.provenance["baseline_config"]["outlier_z_threshold_overrides"] = {"limit_fuel_press_max_time_above_pct": 4.0}
    assert evaluate_filter_health(fas, fleet, [flt], CFG)[0]["status"] == "stable"


def test_monitor_frequency_drift():
    # reference: events on 3 of 12 flights; monitored: on 8 of the last 10
    ref = [(1.0 if i % 4 == 0 else None, 1.0 if i % 4 == 0 else 0.0, None) for i in range(12)]
    mon = [(1.0 if i < 8 else None, 1.0 if i < 8 else 0.0, None) for i in range(10)]
    h = _health(ref + mon, 12)
    assert h["status"] == "drifting" and any("on 8 of your last 10 flights, against 3 of 12 reference flights (25%)" in r for r in h["reasons"])


def test_monitor_review_due():
    h = _health(_TYPICAL + [(1.1, 21.0, None)] * 3, 12, created_engine_hours=50.0)
    assert h["status"] == "review_due" and h["hours_since_review"] > 50


def test_monitor_quiet():
    h = _health(_TYPICAL + [(None, 0.0, None)] * 10, 12)
    assert h["status"] == "quiet"


def test_monitor_collecting_extends_the_reference_forward():
    rows = _TYPICAL[:3] + [(1.1, 21.0, None)] * 1
    h = _health(rows, 2)
    assert h["status"] == "collecting" and len(h["reference"]["flight_ids"]) == 4
    fas, _ = _monitor_fixture(_TYPICAL)
    ids, collecting = effective_reference({"reference": {"flight_ids": ["m000", "m001"]}},
                                          [{"flight_id": fa.flight_id} for fa in fas])
    assert ids == ["m000", "m001", "m002", "m003", "m004"] and not collecting


def test_monitor_priority_breach_over_drift():
    h = _health(_TYPICAL + [(4.0, 60.0, None), (4.0, 60.0, None)], 12)
    assert h["status"] == "breached" and any("spent more of the flight past the limit" in r for r in h["reasons"])


def test_monitor_stratified_comparison_uses_the_flights_band():
    """A filter whose reference spans a cold majority and 10 warm flights:
    warm monitored flights sit within the warm band's reference, so no
    drift — though against all reference flights they'd be 2+ std up."""
    ref = [(1.0, 5.0 + 0.2 * (i % 3), "cold") for i in range(40)] + \
          [(1.0, 30.0 + 0.2 * (i % 3), "warm") for i in range(10)]
    warm = [(1.0, 31.0, "warm"), (1.0, 31.0, "warm")]
    h = _health(ref + warm, 50)
    assert h["status"] == "stable"
    # the same values with no band information would read as drift
    unbanded = _health([(p, v, None) for p, v, _ in ref + warm], 50)
    assert unbanded["status"] == "drifting"


def test_drift_reason_names_the_weather_comparison():
    ref = [(1.0, 5.0 + 0.2 * (i % 3), "cold") for i in range(40)] + \
          [(1.0, 30.0 + 0.2 * (i % 3), "warm") for i in range(10)]
    h = _health(ref + [(1.0, 40.0, "warm"), (1.0, 41.0, "warm")], 50)
    assert h["status"] == "drifting"
    assert "against a typical 30% for your reference flights on warm days (10 flights)" in h["reasons"][0]
    assert h["drift_details"][0]["comparison"] == {"scope": "band", "band": "warm", "n": 10}


def test_non_filterable_limits_say_why_in_plain_words():
    oil = resolve_filter_policy(CAT["oil_press_min"])
    assert not oil["filterable"] and "lubrication problem" in oil["reason"]
    uncapped = resolve_filter_policy({k: v for k, v in CAT["oil_temp_max"].items() if k != "filter_policy"})
    assert "safety caps" in uncapped["reason"] and "max_band_abs" not in uncapped["reason"]


def test_limit_insights_say_whether_they_can_be_filtered():
    fa = _flight([_exc("oil_press_min", "oil_press_psi", "Oil pressure min (>3500 rpm)", 100, 30, 27.0, 29.0,
                       "MIN", "WARNING"), _fp(500, 40, 47.0)])
    ins = {i["limit_id"]: i for i in _limit_topic(evaluate_insights(fa, update_fleet([]), RULES))["insights"]}
    assert ins["oil_press_min"]["filterable"] is False
    assert ins["fuel_press_max"]["filterable"] is True
