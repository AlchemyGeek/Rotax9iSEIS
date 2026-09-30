"""
Contract tests for update_fleet() / FleetAnalysis (Spec 01 §7, §8.4,
§12 acceptance criteria 4, 5, 6).
"""
import json

import jsonschema
import pytest

from slingology_eis.operations import update_fleet

from ..conftest import GOLDEN_DIR, requires_flight_logs, requires_golden_fixtures
from .conftest import load_schema

_SCHEMA = load_schema("fleet_analysis.schema.json")


def test_update_fleet_empty_input():
    fleet = update_fleet([])
    d = fleet.to_dict()
    assert d["flight_ids"] == []
    assert d["metrics"] == {}
    jsonschema.validate(d, _SCHEMA)


@requires_flight_logs
def test_update_fleet_validates_against_schema(real_fleet_analysis):
    if real_fleet_analysis is None:
        pytest.skip("no local flight logs")
    jsonschema.validate(real_fleet_analysis.to_dict(), _SCHEMA)


def test_update_fleet_no_bare_nan():
    fleet = update_fleet([])
    text = json.dumps(fleet.to_dict())
    assert "NaN" not in text
    json.loads(text)


@requires_flight_logs
def test_update_fleet_touches_no_filesystem(monkeypatch, real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")

    def _blocked(*args, **kwargs):
        raise AssertionError("update_fleet must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _blocked)
    fleet = update_fleet(real_flight_analyses)
    assert fleet.fleet_key


# ── Acceptance criterion 4: reproduces current baseline/trend values ────────

@requires_flight_logs
@requires_golden_fixtures
def test_update_fleet_reproduces_golden_baselines(real_fleet_analysis):
    if real_fleet_analysis is None:
        pytest.skip("no local flight logs")

    golden = json.loads((GOLDEN_DIR / "baselines.json").read_text())
    fleet_metrics = real_fleet_analysis.to_dict()["metrics"]

    checked = 0
    for key, golden_entry in golden["baselines"].items():
        if key not in fleet_metrics:
            continue
        checked += 1
        mine = fleet_metrics[key]["baseline"]
        assert mine["n"] == golden_entry["n"], f"{key}: n mismatch"
        if golden_entry.get("mean") is not None:
            assert abs(mine["mean"] - golden_entry["mean"]) < 1e-6, f"{key}: mean mismatch"
            assert abs(mine["std"] - golden_entry["std"]) < 1e-6, f"{key}: std mismatch"
    assert checked >= 9  # sanity: we actually compared something


@requires_flight_logs
@requires_golden_fixtures
def test_update_fleet_reproduces_golden_takeoff_map_model(real_fleet_analysis):
    if real_fleet_analysis is None:
        pytest.skip("no local flight logs")

    golden = json.loads((GOLDEN_DIR / "models.json").read_text())
    golden_map = golden["models"]["takeoff_map"]
    models = {m["id"]: m for m in real_fleet_analysis.to_dict()["models"]}

    if golden_map.get("type") != "linear_regression":
        pytest.skip("golden takeoff_map model has no fit to compare")
    mine = models["takeoff_map"]
    assert mine["n"] == golden_map["n"]
    assert abs(mine["r_squared"] - golden_map["r_squared"]) < 1e-3
    for coef_name, golden_val in golden_map["coefficients"].items():
        assert abs(mine["coefficients"][coef_name] - golden_val) < 1e-3


@requires_flight_logs
def test_update_fleet_by_band_outliers_use_that_bands_own_baseline(real_fleet_analysis):
    """
    R8 (Spec 01 §8.4 v0.13): each by_band.bands[*].outliers entry is
    computed against that band's own all-flights mean/std, at the same
    z-threshold as the unstratified outliers — not the fleet-wide
    baseline. Recomputed independently here from the band's own points
    and stats, both already present in the response.
    """
    if real_fleet_analysis is None:
        pytest.skip("no local flight logs")

    d = real_fleet_analysis.to_dict()
    stratified = {k: v for k, v in d["metrics"].items() if v.get("by_band")}
    if not stratified:
        pytest.skip("no stratified metric in this fleet")

    checked = 0
    for metric_id, metric in stratified.items():
        for band_name, band in metric["by_band"]["bands"].items():
            assert "outliers" in band
            if band["mean"] is None or not band.get("std"):
                continue
            band_points = [p for p in metric["points"] if p.get("band") == band_name]
            expected_ids = {
                p["flight_id"] for p in band_points
                if abs((p["value"] - band["mean"]) / band["std"]) >= 2.0
            }
            actual_ids = {o["flight_id"] for o in band["outliers"]}
            assert actual_ids == expected_ids, f"{metric_id}/{band_name}: outlier set mismatch"
            checked += 1
    assert checked > 0  # sanity: we actually compared some band


@requires_flight_logs
def test_every_limit_metric_is_baselined(real_flight_analyses, real_fleet_analysis):
    """Spec 09 §14 acceptance 3: update_fleet baselines every limit's §5
    metrics with the same functions as existing metrics, stratified where
    the limit says so."""
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    from slingology_eis.baselines import limit_baseline_metric_defs
    defs = limit_baseline_metric_defs(real_flight_analyses[0].limits)
    assert defs
    for key, col, band in defs:
        has_values = any(fa.metrics.get(col, {}).get("value") is not None for fa in real_flight_analyses)
        if not has_values:
            continue
        m = real_fleet_analysis.metrics[key]
        assert m["baseline"]["n"] == len(m["points"])
        assert {"direction", "n"} <= set(m["trend"])
        if band and any(p.get("band") for p in m["points"]):
            assert m["by_band"]["band_kind"] == band


@requires_flight_logs
def test_filter_monitor_replay_fuel_pressure(real_flight_analyses):
    """Spec 09 §14 acceptance 12: replay the log set chronologically,
    set a fuel_press_max filter (+4.0 psi) after the 20th flight, and
    check the status after each later flight. Hand-verified on the N117ZS
    log set: no monitored event exceeds +4.0 psi (so never Breached);
    Review due once 50 engine hours have passed since the filter was set;
    Drifting on the one flight where 10 of the last 10 monitored flights
    had events vs 70% of the reference. Pinned to flights up to
    2026-09-27 so new logs don't move it."""
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    from slingology_eis.filters import evaluate_filter_health, select_reference
    from slingology_eis.limits import limit_catalog, load_engine_config

    cfg = load_engine_config("916iS")
    lim = next(l for l in limit_catalog(cfg) if l["id"] == "fuel_press_max")
    fas = sorted((fa for fa in real_flight_analyses if fa.header["date"] <= "2026-09-27"),
                 key=lambda fa: (fa.header.get("engine_hours_start") or 0, fa.header["date"]))
    k = 20
    flt = {"id": "f", "limit_id": "fuel_press_max", "magnitude": {"mode": "absolute", "value": 4.0},
           "note": "", "created_at": "x", "history": [],
           "reference": {"flight_ids": select_reference(update_fleet(fas[:k]), lim)},
           "created_engine_hours": fas[k - 1].header.get("engine_hours_end")}
    statuses = []
    for m in range(k + 1, len(fas) + 1):
        h = evaluate_filter_health(fas[:m], update_fleet(fas[:m]), [flt], cfg)[0]
        statuses.append(h["status"])
    assert "breached" not in statuses
    first_due = statuses.index("review_due")
    assert set(statuses[:first_due]) == {"stable"}
    assert statuses.count("drifting") == 1
    assert set(statuses[first_due:]) <= {"review_due", "drifting"}
