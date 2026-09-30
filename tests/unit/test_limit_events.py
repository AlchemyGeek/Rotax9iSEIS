"""
Spec 09 Phase 1: stable limit ids, exceedance merging, one insight per
limit per flight, topic thresholds that follow the profile limit, and the
note migration from per-event to per-limit insights.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from slingology_eis import workspace as ws
from slingology_eis.contract import content_hash
from slingology_eis.limits import (
    check_exceedances,
    engine_limits_from_config,
    limit_catalog,
    load_engine_config,
    merge_runs,
    find_runs,
)
from slingology_eis.operations import (
    FlightAnalysis,
    _format_exceedance_text,
    _limit_insight_id,
    evaluate_insights,
    update_fleet,
)
from slingology_eis.rules import validate_rules

ENGINES = ("912iS", "914iS", "915iS", "916iS")


# ── Limit ids (§6.1) ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("engine", ENGINES)
def test_every_profile_limit_has_a_unique_id(engine):
    cfg = load_engine_config(engine)
    ids = [lim["id"] for lim in limit_catalog(cfg)]
    assert len(ids) == len(set(ids))
    assert {"egt_split_high_flow", "egt_split_low_flow", "overboost"} <= set(ids)
    assert all(lim.id for lim in engine_limits_from_config(cfg))


def test_same_limit_same_id_across_engines():
    common = set.intersection(*[{lim["id"] for lim in limit_catalog(load_engine_config(e))} for e in ENGINES])
    assert {"oil_temp_max", "coolant_temp_max", "rpm_takeoff_max", "oil_press_min", "egt4_max"} <= common


def test_missing_limit_id_is_rejected():
    cfg = copy.deepcopy(load_engine_config("916iS"))
    del cfg["limits"][0]["id"]
    with pytest.raises(ValueError, match="no 'id'"):
        engine_limits_from_config(cfg)


def test_duplicate_limit_id_is_rejected():
    cfg = copy.deepcopy(load_engine_config("916iS"))
    cfg["limits"][1]["id"] = cfg["limits"][0]["id"]
    with pytest.raises(ValueError, match="duplicate"):
        engine_limits_from_config(cfg)


def test_duplicate_id_with_computed_limit_is_rejected():
    cfg = copy.deepcopy(load_engine_config("916iS"))
    cfg["limits"][0]["id"] = "overboost"
    with pytest.raises(ValueError, match="duplicate"):
        engine_limits_from_config(cfg)


def test_catalog_carries_overboost_close_call_and_stratification():
    cat = {lim["id"]: lim for lim in limit_catalog(load_engine_config("916iS"))}
    assert cat["overboost"]["limit_value"] == 300
    assert cat["overboost"]["close_call_margin_s"] == 60
    assert cat["oil_temp_max"]["stratify_by"] == "oat_band"
    assert cat["map_max"]["stratify_by"] == "da_band"
    assert cat["fuel_press_max"]["stratify_by"] == "oat_band"  # explicit in the profile (Q7)
    assert cat["fuel_press_min"]["stratify_by"] is None


# ── Merging (§6.2) ────────────────────────────────────────────────────────────

def _frame(values, phase="CRUISE", start="2026-01-01 12:00:00", param="fuel_press_psi"):
    n = len(values)
    return pd.DataFrame({
        "datetime": pd.date_range(start, periods=n, freq="1s"),
        "phase": [phase] * n if isinstance(phase, str) else phase,
        param: values,
    })


def _cfg(gap_s, limits):
    return {"exceedance_merge_gap_s": gap_s, "limits": limits}


_FP_MAX = {"id": "fuel_press_max", "param": "fuel_press_psi", "label": "Fuel pressure maximum",
           "unit": "psi", "max_val": 46.0, "severity": "CAUTION"}


def test_find_runs_positions():
    assert find_runs(pd.Series([False, True, True, False, True, np.nan, True])) == [(1, 2), (4, 4), (6, 6)]
    assert find_runs(pd.Series([False, False])) == []


def test_short_dips_merge_into_one_event():
    # 10 s over, 5 s back at the limit, 10 s over again
    values = [47.0] * 10 + [46.0] * 5 + [47.5] * 10
    events = check_exceedances(_frame(values), _cfg(30, [_FP_MAX]))
    assert len(events) == 1
    e = events[0]
    assert e.duration_s == 25
    assert e.observed_value == 47.5
    assert e.excess == pytest.approx(1.5)
    assert e.limit_id == "fuel_press_max"


def test_long_recovery_ends_the_event():
    values = [47.0] * 10 + [45.0] * 30 + [47.0] * 10
    events = check_exceedances(_frame(values), _cfg(30, [_FP_MAX]))
    assert len(events) == 2  # 30 s within the limit is not < 30


def test_no_merge_gap_keeps_pre_spec09_behaviour():
    values = [47.0] * 10 + [46.0] * 2 + [47.0] * 10
    assert len(check_exceedances(_frame(values), {"limits": [_FP_MAX]})) == 2


def test_per_limit_gap_override():
    lim = {**_FP_MAX, "exceedance_merge_gap_s": 0}
    values = [47.0] * 10 + [46.0] * 2 + [47.0] * 10
    assert len(check_exceedances(_frame(values), _cfg(30, [lim]))) == 2


def test_merge_gap_is_measured_in_time_not_rows():
    # Phase filtering makes rows non-contiguous: two CRUISE stretches 2 rows
    # apart in the filtered frame but 60 s apart in time must not merge.
    values = [47.0] * 5 + [47.0] * 60 + [47.0] * 5
    phases = ["CRUISE"] * 5 + ["TAXI"] * 60 + ["CRUISE"] * 5
    lim = {**_FP_MAX, "phases": ["CRUISE"]}
    events = check_exceedances(_frame(values, phase=phases), _cfg(30, [lim]))
    assert len(events) == 2


def test_merging_happens_before_min_duration():
    # Three 4 s spikes with 3 s dips: each alone is under min_duration_s=10;
    # merged they're one 18 s event, which the duration check then keeps.
    lim = {**_FP_MAX, "min_duration_s": 10}
    values = ([47.0] * 4 + [45.0] * 3) * 2 + [47.0] * 4
    assert check_exceedances(_frame(values), {"limits": [lim]}) == []
    events = check_exceedances(_frame(values), _cfg(30, [lim]))
    assert len(events) == 1 and events[0].duration_s == 18


def test_min_limit_excess_is_positive():
    lim = {"id": "fuel_press_min", "param": "fuel_press_psi", "label": "Fuel pressure minimum",
           "unit": "psi", "min_val": 42.0, "severity": "WARNING"}
    events = check_exceedances(_frame([40.5] * 5), _cfg(30, [lim]))
    assert events[0].excess == pytest.approx(1.5)


def test_merge_runs_respects_gap():
    times = pd.Series(pd.date_range("2026-01-01", periods=100, freq="1s"))
    runs = [(0, 4), (10, 14), (60, 64)]
    assert merge_runs(times, runs, 30) == [(0, 14), (60, 64)]
    assert merge_runs(times, runs, 0) == runs


# ── One insight per limit (§10.1), topic thresholds (§10.2) ───────────────────

def _exc(limit_id, param, label, start_s, dur_s, observed, limit_value, limit_type="MAX", severity="CAUTION", unit="psi"):
    start = pd.Timestamp("2026-01-01 12:00:00") + pd.Timedelta(seconds=start_s)
    excess = observed - limit_value if limit_type == "MAX" else limit_value - observed
    return {
        "limit_id": limit_id, "event_id": f"{limit_id}@{start.isoformat()}", "excess": excess,
        "param": param, "label": label, "unit": unit, "severity": severity, "limit_type": limit_type,
        "limit_value": limit_value, "observed_value": observed, "start_utc": start.isoformat(),
        "elapsed_s": float(start_s), "duration_s": float(dur_s), "time_limit_s": None, "note": "",
    }


def _flight(exceedances, metrics=None, limits=None, flight_id="f1"):
    return FlightAnalysis(
        flight_id=flight_id, analysis_key="k", source_keys=["s"],
        header={"date": "2026-01-01", "start_utc": "2026-01-01T12:00:00", "engine_hours_start": 10.0},
        metrics=metrics or {}, exceedances=exceedances, provenance={},
        limits=limit_catalog(load_engine_config("916iS")) if limits is None else limits,
    )


@pytest.fixture(scope="module")
def rules():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[2] / "insight_rules.json").read_text())


def _topic(iset, topic_id):
    return next(t for t in iset.topics if t["topic_id"] == topic_id)


def test_one_insight_per_limit_carrying_its_events(rules):
    excs = [
        _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 100, 40, 46.4, 46.0),
        _exc("volts_min", "main_volts", "Bus voltage minimum", 150, 5, 11.2, 11.5, "MIN", unit="V"),
        _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 900, 120, 50.4, 46.0),
    ]
    fa = _flight(excs)
    iset = evaluate_insights(fa, update_fleet([]), rules)
    insights = _topic(iset, "limit_exceedances")["insights"]
    assert [i["limit_id"] for i in insights] == ["fuel_press_max", "volts_min"]
    fp = insights[0]
    assert [e["event_id"] for e in fp["events"]] == [excs[0]["event_id"], excs[2]["event_id"]]
    assert all(e["suppressed_by"] is None for e in fp["events"])
    assert "2 events" in fp["message"]["text"] and "50.4" in fp["message"]["text"]
    assert len(fp["evidence"]) == 2 and fp["evidence"][0]["kind"] == "series_window"
    assert fp["id"] == _limit_insight_id("f1", "fuel_press_max", "exceedance")


def test_limit_insight_id_is_stable_across_wording(rules):
    a = _flight([_exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 100, 40, 46.4, 46.0)])
    b = _flight([_exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 100, 90, 48.0, 46.0)])
    ia = _topic(evaluate_insights(a, update_fleet([]), rules), "limit_exceedances")["insights"][0]
    ib = _topic(evaluate_insights(b, update_fleet([]), rules), "limit_exceedances")["insights"][0]
    assert ia["message"]["text"] != ib["message"]["text"]
    assert ia["id"] == ib["id"]


def test_note_attaches_to_per_limit_insight(rules):
    fa = _flight([_exc("volts_min", "main_volts", "Bus voltage minimum", 150, 5, 11.2, 11.5, "MIN", unit="V")])
    iid = _limit_insight_id("f1", "volts_min", "exceedance")
    iset = evaluate_insights(fa, update_fleet([]), rules,
                             annotations=[{"ref": {"kind": "insight", "insight_id": iid}, "note": "known"}])
    assert _topic(iset, "limit_exceedances")["insights"][0]["note"] == "known"


def _oil_metric(v):
    return {"oil_temp_max_f": {"id": "oil_temp_max_f", "value": v}}


def _oil_fleet():
    """A fleet whose oil_temp_peak baseline exists — topics only report
    (threshold included) once there is a personal baseline."""
    from slingology_eis.operations import FleetAnalysis
    points = [{"flight_id": f"o{i}", "date": "2025-12-01", "x": float(i), "value": 200.0 + i} for i in range(12)]
    return FleetAnalysis(fleet_key="fk", flight_ids=[p["flight_id"] for p in points],
                         metrics={"oil_temp_peak": {"metric_id": "oil_temp_peak", "points": points, "trend": {}}},
                         provenance={"baseline_config": {}})


def test_topic_threshold_fires_only_with_a_limit_event(rules):
    # A 252°F peak with no oil_temp_max event (e.g. excluded by the limit's
    # own phase or duration rules) no longer fires the topic threshold.
    fa = _flight([], metrics=_oil_metric(252.0))
    oil = _topic(evaluate_insights(fa, _oil_fleet(), rules), "oil_temp_peak")["insights"]
    assert [i for i in oil if i["trigger"] == "threshold"] == []

    fa2 = _flight([_exc("oil_temp_max", "oil_temp_f", "Oil temp maximum", 100, 30, 252.0, 248.0,
                        severity="WARNING", unit="°F")], metrics=_oil_metric(252.0))
    oil2 = _topic(evaluate_insights(fa2, _oil_fleet(), rules), "oil_temp_peak")["insights"]
    assert [i["message"]["text"] for i in oil2 if i["trigger"] == "threshold"] == ["⚠ Exceeded OM limit of 248°F."]


def test_topic_threshold_uses_the_profiles_value():
    # 915iS oil_temp_max is 266°F, not the 248°F rules v1.2 hard-coded.
    cat = {lim["id"]: lim for lim in limit_catalog(load_engine_config("915iS"))}
    assert cat["oil_temp_max"]["limit_value"] == 266.0


def test_pre_spec09_flight_keeps_legacy_threshold(rules):
    fa = _flight([], metrics=_oil_metric(252.0), limits=[])
    oil = _topic(evaluate_insights(fa, _oil_fleet(), rules), "oil_temp_peak")["insights"]
    assert [i["message"]["text"] for i in oil if i["trigger"] == "threshold"] == ["⚠ Exceeded OM limit of 248°F."]


def test_unresolved_limit_ref_is_a_diagnostic_not_an_insight(rules):
    bad = copy.deepcopy(rules)
    for trig in bad["rules"]["oil_temp_peak"]["triggers"]:
        if trig["type"] == "threshold":
            trig["limit_ref"] = "no_such_limit"
    fa = _flight([_exc("oil_temp_max", "oil_temp_f", "Oil temp maximum", 100, 30, 252.0, 248.0,
                       severity="WARNING", unit="°F")], metrics=_oil_metric(252.0))
    iset = evaluate_insights(fa, _oil_fleet(), bad)
    assert [i for i in _topic(iset, "oil_temp_peak")["insights"] if i["trigger"] == "threshold"] == []
    assert any(d["code"] == "RULES_LIMIT_REF_UNRESOLVED" for d in iset.header_warnings)


def test_validate_rules_checks_limit_ref(rules):
    ids = {lim["id"] for lim in limit_catalog(load_engine_config("916iS"))}
    assert validate_rules(rules, limit_ids=ids) == []
    bad = copy.deepcopy(rules)
    bad["rules"]["oil_temp_peak"]["triggers"][0]["limit_ref"] = "nope"
    assert any(d["code"] == "RULES_LIMIT_REF_UNRESOLVED" for d in validate_rules(bad, limit_ids=ids))


def test_shipped_rules_have_no_numeric_thresholds(rules):
    for topic_id, topic in rules["rules"].items():
        for trig in topic["triggers"]:
            if trig["type"] == "threshold":
                assert "limit" not in trig, topic_id


@pytest.mark.parametrize("margin,ob_max,expected", [
    (60, 235, None),          # 916iS: close call from 300 - 60 = 240 s
    (60, 245, "Close call"),
    (40, 245, None),          # a narrower margin moves the close call to 260 s
    (60, 310, "Exceeded"),
])
def test_overboost_close_call_follows_profile_margin(rules, margin, ob_max, expected):
    fa = _flight([], metrics={"overboost_max_block_s": {"id": "overboost_max_block_s", "value": ob_max},
                              "overboost_total_s": {"id": "overboost_total_s", "value": ob_max}})
    fa.limits = [dict(lim, close_call_margin_s=margin) if lim["id"] == "overboost" else lim for lim in fa.limits]
    texts = [i["message"]["text"] for i in _topic(evaluate_insights(fa, update_fleet([]), rules), "overboost_time")["insights"]]
    if expected is None:
        assert texts == []
    else:
        assert len(texts) == 1 and expected in texts[0]


# ── Note migration (Q6) ───────────────────────────────────────────────────────

def test_notes_on_per_event_insights_move_to_the_per_limit_insight(tmp_path):
    ws_dir = tmp_path
    old_excs = [
        _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 100, 40, 46.4, 46.0),
        _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 900, 60, 47.0, 46.0),
        _exc("volts_min", "main_volts", "Bus voltage minimum", 150, 5, 11.2, 11.5, "MIN", unit="V"),
    ]
    for e in old_excs:  # pre-Spec-09 analysis shape
        for k in ("limit_id", "event_id", "excess"):
            e.pop(k)
    old = _flight(old_excs, limits=[])

    def _old_id(e):
        return content_hash({"flight_id": "f1", "topic_id": "limit_exceedances", "trigger": "threshold",
                             "text": f"⚠ {_format_exceedance_text(e)}"})[:16]

    ws.save_annotation(ws_dir, "f1", {"kind": "insight", "insight_id": _old_id(old_excs[0])}, "sender reads high")
    ws.save_annotation(ws_dir, "f1", {"kind": "insight", "insight_id": _old_id(old_excs[1])}, "tank switch")
    ws.save_annotation(ws_dir, "f1", {"kind": "insight", "insight_id": _old_id(old_excs[2])}, "starter")
    ws.save_annotation(ws_dir, "f1", {"kind": "ecu_run", "ref": "x"}, "unrelated")

    fresh = _flight([])
    assert ws.migrate_limit_annotations(ws_dir, old, fresh) == 3
    notes = {a["ref"].get("insight_id"): a["note"] for a in ws.load_annotations(ws_dir)["annotations"]}
    assert notes[_limit_insight_id("f1", "fuel_press_max", "exceedance")] == "sender reads high\n\ntank switch"
    assert notes[_limit_insight_id("f1", "volts_min", "exceedance")] == "starter"
    assert len(ws.load_annotations(ws_dir)["annotations"]) == 3
    # idempotent: an analysis that already has limit ids is left alone
    assert ws.migrate_limit_annotations(ws_dir, fresh, fresh) == 0


# ── Per-limit metrics (§5, Phase 2) ──────────────────────────────────────────

from slingology_eis.baselines import limit_baseline_metric_defs  # noqa: E402
from slingology_eis.limits import engine_running_s, per_limit_metrics  # noqa: E402

_CAT_916 = limit_catalog(load_engine_config("916iS"))


def _metrics_for(excs, running_s=1000.0, channels=("fuel_press_psi", "main_volts", "rpm"), ob=None):
    return per_limit_metrics(excs, _CAT_916, running_s, set(channels), overboost_max_block_s=ob)


def test_peak_excess_and_time_above_share():
    m = _metrics_for([
        _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 100, 40, 46.4, 46.0),
        _exc("fuel_press_max", "fuel_press_psi", "Fuel pressure maximum", 900, 60, 47.5, 46.0),
    ])
    assert m["lim_fuel_press_max_peak_excess"]["value"] == pytest.approx(1.5)
    assert m["lim_fuel_press_max_time_above_pct"]["value"] == pytest.approx(10.0)
    assert m["lim_fuel_press_max_peak_excess"]["unit"] == "psi"


def test_no_event_means_missing_peak_and_zero_share():
    m = _metrics_for([])
    assert m["lim_fuel_press_max_peak_excess"]["value"] is None
    assert m["lim_fuel_press_max_peak_excess"]["missing"] == "NOT_APPLICABLE"
    assert m["lim_fuel_press_max_time_above_pct"]["value"] == 0.0


def test_channel_missing_and_unknown_running_time():
    m = _metrics_for([], channels=("rpm",))
    assert m["lim_fuel_press_max_time_above_pct"]["missing"] == "CHANNEL_MISSING"
    m = _metrics_for([], running_s=None)
    assert m["lim_fuel_press_max_time_above_pct"]["missing"] == "INSUFFICIENT_DATA"


def test_overboost_gets_block_metric_only():
    m = _metrics_for([], ob=250)
    assert m["lim_overboost_block_s"]["value"] == 250
    assert not any(k.startswith("lim_overboost_") and k != "lim_overboost_block_s" for k in m)


def test_limits_never_checked_get_no_metrics():
    m = _metrics_for([])
    assert not any("oil_temp_optimal_low" in k for k in m)  # report_in_exceedances: false


def test_engine_running_time_excludes_pre_start_and_shutdown():
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-01-01 12:00:00", periods=100, freq="1s"),
        "phase": ["PRE_START"] * 10 + ["TAXI"] * 30 + ["CRUISE"] * 50 + ["SHUTDOWN"] * 10,
    })
    assert engine_running_s(df) == 80


def test_limit_metric_defs_are_generated_from_the_catalog():
    defs = {key: (col, band) for key, col, band in limit_baseline_metric_defs(_CAT_916)}
    assert defs["limit_fuel_press_max_peak_excess"] == ("lim_fuel_press_max_peak_excess", "oat_band")
    assert defs["limit_oil_temp_max_time_above_pct"] == ("lim_oil_temp_max_time_above_pct", "oat_band")
    assert defs["limit_volts_min_time_above_pct"] == ("lim_volts_min_time_above_pct", None)
    assert defs["limit_overboost_block_s"] == ("lim_overboost_block_s", "da_band")


def _fleet_flight(i, peak, pct, band):
    metrics = {
        "lim_fuel_press_max_peak_excess": {"id": "lim_fuel_press_max_peak_excess", "value": peak},
        "lim_fuel_press_max_time_above_pct": {"id": "lim_fuel_press_max_time_above_pct", "value": pct},
        "oat_band": {"id": "oat_band", "value": band},
    }
    for k in ("takeoff_map_inhg", "takeoff_pressure_alt_ft", "takeoff_oat_c"):
        metrics[k] = {"id": k, "value": None}
    return FlightAnalysis(
        flight_id=f"f{i:02d}", analysis_key=f"k{i}", source_keys=[f"s{i}"],
        header={"date": f"2026-01-{i + 1:02d}", "start_utc": "x", "engine_hours_start": 10.0 + i},
        metrics=metrics, provenance={}, limits=_CAT_916,
    )


def test_update_fleet_baselines_per_limit_metrics_like_any_other():
    fas = [_fleet_flight(i, 0.3 + 0.01 * i if i % 3 else None, 20.0 + i, "cold" if i < 6 else "mild")
           for i in range(20)]
    fleet = update_fleet(fas)
    peak = fleet.metrics["limit_fuel_press_max_peak_excess"]
    pct = fleet.metrics["limit_fuel_press_max_time_above_pct"]
    # flights with no event (None) aren't points of peak_excess; every flight is a point of the share
    assert len(peak["points"]) == sum(1 for i in range(20) if i % 3)
    assert len(pct["points"]) == 20
    assert pct["trend"]["direction"] == "increasing"
    assert set(pct["by_band"]["bands"]) == {"cold", "mild"}
    assert pct["by_band"]["band_kind"] == "oat_band"
    # no BASELINE_LOW_N noise for metrics without insight rules
    assert not any(q["refs"].get("metric_id", "").startswith("limit_") for q in fleet.quality)


def test_per_limit_outliers_use_the_metric_threshold():
    fas = [_fleet_flight(i, None, 20.0, "mild") for i in range(15)] + [_fleet_flight(15, None, 60.0, "mild")]
    base = update_fleet(fas)
    assert [o["flight_id"] for o in base.metrics["limit_fuel_press_max_time_above_pct"]["outliers"]] == ["f15"]
    loose = update_fleet(fas, baseline_config={
        "membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 2.0,
        "outlier_z_threshold_overrides": {"limit_fuel_press_max_time_above_pct": 10.0}})
    assert loose.metrics["limit_fuel_press_max_time_above_pct"]["outliers"] == []
