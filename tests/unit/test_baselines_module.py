"""
Unit tests for the Stage 2b fleet baseline/trend/model construction in
slingology_eis/baselines.py. Synthetic metrics table, not real flight data.
"""
import pandas as pd
import pytest

from slingology_eis.baselines import build_baselines, build_models, build_takeoff_map_model


def _metrics(n=3, with_takeoff=True):
    rows = []
    for i in range(n):
        row = {
            "date": f"2026-01-{i+1:02d}",
            "engine_hours": 10.0 + i,
            "egt_spread_mean_f": 50.0 + i,
            "oat_band": "mild",
            "da_band": "low",
            "cruise_nmpg": 20.0 + i,
        }
        if with_takeoff:
            row.update({
                "takeoff_map_inhg": 44.0 + i * 0.1,
                "takeoff_pressure_alt_ft": 100.0 + i * 10,
                "takeoff_oat_c": 15.0 + i,
            })
        rows.append(row)
    return pd.DataFrame(rows)


def test_build_baselines_shape_and_values():
    metrics = _metrics(n=4)
    doc = build_baselines(metrics, "916iS")

    assert doc["engine"] == "916iS"
    assert doc["flight_count"] == 4
    assert "generated_at" not in doc  # no clock reads — caller adds it
    assert doc["engine_hours_range"] == [10.0, 13.0]

    egt = doc["baselines"]["egt_spread"]
    assert egt["n"] == 4
    assert egt["mean"] == pytest.approx(51.5)
    assert "by_band" in egt  # oat_band stratification present
    assert len(egt["raw"]) == 4

    # A metric column not present in the synthetic table is skipped, not errored
    assert "oil_temp_peak" not in doc["baselines"]


def test_build_baselines_empty_engine_hours():
    metrics = pd.DataFrame({"date": [], "engine_hours": [], "egt_spread_mean_f": []})
    doc = build_baselines(metrics, "916iS")
    assert doc["engine_hours_range"] is None
    assert doc["flight_count"] == 0


def test_build_takeoff_map_model_insufficient_data():
    metrics = _metrics(n=3)  # < 5 rows
    model = build_takeoff_map_model(metrics)
    assert model["n"] == 3
    assert "note" in model
    assert "type" not in model
    assert model["raw"][0]["map_inhg"] == 44.0


def test_build_takeoff_map_model_fits_regression_with_enough_data():
    metrics = _metrics(n=6)
    model = build_takeoff_map_model(metrics)
    assert model["n"] == 6
    assert model["type"] == "linear_regression"
    assert set(model["coefficients"].keys()) == {"intercept", "pressure_alt_ft", "oat_c"}
    assert model["r_squared"] is not None


def test_build_models_wraps_takeoff_map():
    metrics = _metrics(n=6)
    doc = build_models(metrics)
    assert doc["flight_count"] == 6
    assert "generated_at" not in doc
    assert doc["models"]["takeoff_map"]["n"] == 6


def test_build_baselines_no_file_io_or_clock_reads(tmp_path, monkeypatch):
    # Guard against regressions that sneak in a Path()/open()/date.today() —
    # this module must stay pure per Spec 01 principle 2.
    original_open = open

    def _blocked_open(*args, **kwargs):
        raise AssertionError("build_baselines must not touch the filesystem")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.open", _blocked_open)
    try:
        build_baselines(_metrics(n=4), "916iS")
        build_models(_metrics(n=6))
    finally:
        monkeypatch.setattr("builtins.open", original_open)
