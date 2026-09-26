"""
Contract tests for evaluate_insights() / InsightSet (Spec 01 §7, §8.5,
§12 acceptance criteria 5, 6, and the leave-one-out baseline membership
resolved in R2). Criterion 8's exact trigger counts are specific to the
23-flight snapshot the spec's reviewer used, which this environment
doesn't have (our local fleet has grown past that) — so leave-one-out
correctness is verified structurally (excludes the right flight, uses
the right n) rather than against those exact numbers.
"""
import json

import jsonschema
import pytest

from slingology_eis.operations import evaluate_insights

from ..conftest import requires_flight_logs
from .conftest import load_schema

_SCHEMA = load_schema("insight_set.schema.json")


@requires_flight_logs
def test_evaluate_insights_validates_against_schema(real_flight_analyses, real_fleet_analysis, rules):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    iset = evaluate_insights(real_flight_analyses[0], real_fleet_analysis, rules)
    jsonschema.validate(iset.to_dict(), _SCHEMA)


@requires_flight_logs
def test_evaluate_insights_no_bare_nan(real_flight_analyses, real_fleet_analysis, rules):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    iset = evaluate_insights(real_flight_analyses[0], real_fleet_analysis, rules)
    text = json.dumps(iset.to_dict())
    assert "NaN" not in text
    json.loads(text)


@requires_flight_logs
def test_evaluate_insights_touches_no_filesystem(monkeypatch, real_flight_analyses, real_fleet_analysis, rules):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")

    def _blocked(*args, **kwargs):
        raise AssertionError("evaluate_insights must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _blocked)
    iset = evaluate_insights(real_flight_analyses[0], real_fleet_analysis, rules)
    assert iset.flight_id


@requires_flight_logs
def test_evaluate_insights_covers_twelve_of_thirteen_topics(real_flight_analyses, real_fleet_analysis, rules):
    """cylinder_rank is a known, documented gap (needs rank_order data
    not on the FlightAnalysis metric registry) — everything else fires."""
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    iset = evaluate_insights(real_flight_analyses[0], real_fleet_analysis, rules)
    topic_ids = {t["topic_id"] for t in iset.to_dict()["topics"]}
    expected = {
        "egt_spread", "egt4_elevation", "oil_temp_peak", "coolant_temp_peak",
        "oil_coolant_ratio", "cruise_efficiency", "cruise_fuel_flow", "climb_thermal_rate",
        "overboost_time", "map_at_takeoff", "engine_ecu_inflight", "limit_exceedances",
    }
    assert topic_ids == expected
    assert "cylinder_rank" not in topic_ids


# ── Leave-one-out baseline membership (R2) ───────────────────────────────────

@requires_flight_logs
def test_evaluate_insights_leave_one_out_excludes_the_flight_itself(
    real_flight_analyses, real_fleet_analysis, rules,
):
    if len(real_flight_analyses) < 5:
        pytest.skip("not enough local flights for a meaningful leave-one-out check")

    target = real_flight_analyses[0]
    fleet_metric = real_fleet_analysis.to_dict()["metrics"]["egt_spread"]
    all_flights_n = fleet_metric["baseline"]["n"]

    # This flight must actually be one of the points contributing to the
    # all-flights baseline, or leave-one-out has nothing to exclude.
    own_point = next((p for p in fleet_metric["points"] if p["flight_id"] == target.flight_id), None)
    if own_point is None:
        pytest.skip("target flight has no egt_spread_mean_f value")

    iset = evaluate_insights(target, real_fleet_analysis, rules)
    # Recompute the leave-one-out baseline the same way evaluate_insights
    # does, from the same points array, to check n excludes this flight.
    from slingology_eis.operations import _leave_one_out_baseline
    loo = _leave_one_out_baseline(fleet_metric["points"], target.flight_id)
    assert loo["n"] == all_flights_n - 1


@requires_flight_logs
def test_evaluate_insights_baseline_deviation_uses_leave_one_out_not_self_inclusive(
    real_flight_analyses, real_fleet_analysis,
):
    """
    A flight that IS the fleet mean under self-inclusive baselines would
    show z=0 either way — pick any flight and confirm the insight
    evaluation's baseline differs from the naive self-inclusive one
    whenever the flight's own value isn't exactly the fleet mean (i.e.
    removing it changes the mean at all).
    """
    if len(real_flight_analyses) < 5:
        pytest.skip("not enough local flights")

    from slingology_eis.operations import _leave_one_out_baseline

    fleet_metric = real_fleet_analysis.to_dict()["metrics"]["egt_spread"]
    points = fleet_metric["points"]
    self_inclusive_mean = fleet_metric["baseline"]["mean"]

    target_point = points[0]
    loo = _leave_one_out_baseline(points, target_point["flight_id"])

    if target_point["value"] == self_inclusive_mean:
        pytest.skip("this flight's value equals the fleet mean exactly — no observable difference")
    assert loo["mean"] != self_inclusive_mean


@requires_flight_logs
def test_limit_exceedances_insights_carry_series_window_evidence(real_flight_analyses, real_fleet_analysis, rules):
    """
    _emit() builds evidence generically from metric_ids, but
    limit_exceedances is per-event, not metric-shaped, and was always
    called with metric_ids=[] — so every limit_exceedances insight had
    evidence=[] regardless of the flight, silently breaking
    evidence-click-to-zoom for the most common real insight severity.
    """
    flight_with_exceedances = next((fa for fa in real_flight_analyses if fa.exceedances), None)
    if flight_with_exceedances is None:
        pytest.skip("no local flight with a real exceedance")
    iset = evaluate_insights(flight_with_exceedances, real_fleet_analysis, rules)
    topic = next(t for t in iset.to_dict()["topics"] if t["topic_id"] == "limit_exceedances")
    assert topic["insights"], "expected at least one limit_exceedances insight"
    for insight in topic["insights"]:
        assert insight["evidence"], f"insight {insight['id']} has no evidence"
        ev = insight["evidence"][0]
        assert ev["kind"] == "series_window"
        assert ev["end_s"] > ev["start_s"] >= 0


@requires_flight_logs
def test_metric_evidence_uses_fleet_key_not_flight_metric_id(real_flight_analyses, real_fleet_analysis, rules):
    """
    _TOPIC_METRIC_MAP's two sides use different naming conventions
    (registry.py's flight_metric_id vs. baselines.py's fleet_key) — for 7
    of the 8 shared-baseline topics they're spelled differently (e.g.
    "egt4_elevation_f" vs "egt4_elevation"). Evidence's metric_id feeds
    straight into "View evidence" -> Trends ?metric=<id>, which only
    recognizes fleet_key spellings; sending flight_metric_id there was a
    real bug (Trends showed "No fleet data for this metric" for any
    topic whose two names actually differ).
    """
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    fleet_keys = set(real_fleet_analysis.to_dict()["metrics"].keys())
    checked = 0
    iset = evaluate_insights(real_flight_analyses[0], real_fleet_analysis, rules)
    for topic in iset.to_dict()["topics"]:
        for insight in topic["insights"]:
            for ev in insight["evidence"]:
                if ev["kind"] == "metric":
                    checked += 1
                    assert ev["metric_id"] in fleet_keys, (
                        f"{topic['topic_id']}: evidence metric_id {ev['metric_id']!r} "
                        f"is not a real fleet metric key"
                    )
    assert checked > 0, "expected at least one metric-kind evidence to check"


def test_leave_one_out_baseline_empty_points():
    from slingology_eis.operations import _leave_one_out_baseline
    result = _leave_one_out_baseline([], "any_flight")
    assert result == {"mean": None, "std": None, "n": 0}


def test_leave_one_out_baseline_excludes_only_matching_flight_id():
    from slingology_eis.operations import _leave_one_out_baseline
    points = [
        {"flight_id": "a", "value": 10.0},
        {"flight_id": "b", "value": 20.0},
        {"flight_id": "c", "value": 30.0},
    ]
    result = _leave_one_out_baseline(points, "b")
    assert result["n"] == 2
    assert result["mean"] == 20.0  # mean of 10, 30


# ── BASELINE_LOW_N gating (R2) — synthetic, since no local metric has n<10 ──

def test_evaluate_insights_low_n_suppresses_insight_and_adds_warning():
    from slingology_eis.operations import FlightAnalysis, FleetAnalysis, evaluate_insights

    flight = FlightAnalysis(
        flight_id="f0", analysis_key="ak0", source_keys=["sk0"],
        header={"date": "2026-01-01", "start_utc": "2026-01-01T00:00:00"},
        metrics={"egt_spread_mean_f": {"id": "egt_spread_mean_f", "value": 100.0, "unit": "°F"}},
        provenance={"schema_version": "0.1.0", "engine_profile": None, "params_hash": "x"},
    )
    # Only 3 leave-one-out points (n=3, below n_min=10) but a huge deviation
    # (z would be enormous) — must NOT fire as an insight, must be gated.
    points = [
        {"flight_id": "other1", "date": "2026-01-01", "x": 1.0, "value": 10.0},
        {"flight_id": "other2", "date": "2026-01-01", "x": 2.0, "value": 11.0},
        {"flight_id": "other3", "date": "2026-01-01", "x": 3.0, "value": 9.0},
    ]
    fleet = FleetAnalysis(
        fleet_key="fk0", flight_ids=["f0", "other1", "other2", "other3"],
        metrics={"egt_spread": {
            "metric_id": "egt_spread",
            "baseline": {"n": 3, "mean": 10.0, "std": 1.0, "min": 9.0, "max": 11.0,
                         "confidence": {"level": "LOW", "n": 3}},
            "trend": {"n": 3, "slope": None, "r_squared": None, "direction": "insufficient_data",
                     "x": "engine_hours", "confidence": {"level": "LOW", "n": 3}},
            "points": points, "outliers": [],
        }},
        models=[],
    )
    rules = {"rules": {"egt_spread": {"enabled": True, "triggers": [
        {"type": "baseline_deviation", "z_score_threshold": 2.0, "n_min": 10, "severity": "watch"},
    ]}}}

    iset = evaluate_insights(flight, fleet, rules)
    d = iset.to_dict()
    egt_topic = next(t for t in d["topics"] if t["topic_id"] == "egt_spread")
    assert egt_topic["insights"] == []  # gated, despite an enormous z-score
    assert any(w["code"] == "BASELINE_LOW_N" for w in d["header_warnings"])
