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
