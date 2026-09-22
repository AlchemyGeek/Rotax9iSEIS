"""
Unit tests for the Stage 2c per-flight topic functions in
slingology_eis/topics.py. Synthetic inputs only.
"""
from slingology_eis import topics


# ── Shared helpers ────────────────────────────────────────────────────────

def test_z_score_zero_std():
    assert topics.z_score(10, 5, 0) == 0.0


def test_z_score_basic():
    assert topics.z_score(15, 10, 5) == 1.0


def test_baseline_triggered_above_threshold():
    triggered, text = topics.baseline_triggered(20, {"mean": 10, "std": 5}, {"z_score_threshold": 2.0})
    assert triggered
    assert "above" in text and "⚠" in text


def test_baseline_triggered_below_threshold_direction():
    triggered, text = topics.baseline_triggered(0, {"mean": 10, "std": 5}, {"z_score_threshold": 2.0})
    assert triggered
    assert "below" in text and "↓" in text


def test_baseline_triggered_not_triggered():
    triggered, text = topics.baseline_triggered(11, {"mean": 10, "std": 5}, {"z_score_threshold": 2.0})
    assert not triggered
    assert text == ""


def test_baseline_triggered_missing_data():
    triggered, text = topics.baseline_triggered(None, {"mean": 10, "std": 5}, {})
    assert not triggered
    triggered, text = topics.baseline_triggered(20, {"mean": None}, {})
    assert not triggered


def test_trend_triggered_matches_direction():
    b = {"trend": {"direction": "increasing", "r_squared": 0.8, "n": 15, "slope": 0.5}}
    triggered, text = topics.trend_triggered(b, {"direction": "increasing", "r2_min": 0.5, "n_min": 10})
    assert triggered
    assert "increasing" in text


def test_trend_triggered_wrong_direction():
    b = {"trend": {"direction": "decreasing", "r_squared": 0.8, "n": 15, "slope": -0.5}}
    triggered, _ = topics.trend_triggered(b, {"direction": "increasing"})
    assert not triggered


def test_trend_triggered_below_r2_or_n():
    b = {"trend": {"direction": "increasing", "r_squared": 0.1, "n": 15}}
    triggered, _ = topics.trend_triggered(b, {"direction": "increasing", "r2_min": 0.5})
    assert not triggered


def test_confidence_note_thresholds():
    assert "still building" in topics.confidence_note({"n": 1})
    assert "low confidence" in topics.confidence_note({"n": 5})
    assert topics.confidence_note({"n": 15}) == ""


def test_predict_takeoff_map_no_coefficients():
    assert topics.predict_takeoff_map({}, 1000, 15) is None


def test_predict_takeoff_map_linear():
    model = {"coefficients": {"intercept": 40, "pressure_alt_ft": 0.001, "oat_c": 0.1}}
    assert topics.predict_takeoff_map(model, 1000, 20) == 40 + 1.0 + 2.0


# ── Topic functions ───────────────────────────────────────────────────────

def test_egt_spread_insufficient_data():
    result = topics.egt_spread(None, 392, {}, [])
    assert result["insights"] == []
    assert "Insufficient" in result["analysis"]


def test_egt_spread_disabled_suppresses_all_triggers():
    b = {"mean": 50, "std": 5, "n": 20}
    rule = {"type": "baseline_deviation", "z_score_threshold": 2.0}
    result = topics.egt_spread(80, 392, b, [rule], enabled=False)
    assert result["insights"] == []


def test_egt_spread_fires_baseline_and_trend_together():
    b = {"mean": 50, "std": 5, "n": 20,
         "trend": {"direction": "increasing", "r_squared": 0.8, "n": 15, "slope": 0.5}}
    rules = [
        {"type": "baseline_deviation", "z_score_threshold": 2.0},
        {"type": "trend", "direction": "increasing", "r2_min": 0.5, "n_min": 10},
    ]
    result = topics.egt_spread(80, 392, b, rules)
    assert len(result["insights"]) == 2


def test_cylinder_rank_stable():
    result = topics.cylinder_rank(["egt4_f", "egt1_f"], True, "Stable in 30/30 fleet flights.")
    assert "EGT4" in result["analysis"]
    assert result["insights"] == []


def test_cylinder_rank_unstable_fires_insight():
    result = topics.cylinder_rank(["egt2_f"], False, "")
    assert result["insights"]
    assert "instability" in result["insights"][0].lower()


def test_cylinder_rank_no_data():
    result = topics.cylinder_rank([], None, "")
    assert result["insights"] == []
    assert "Insufficient" in result["analysis"]


def test_overboost_exceeded():
    result = topics.overboost(320, 320, 300, True)
    assert "Exceeded" in result["insights"][0]


def test_overboost_close_call():
    result = topics.overboost(250, 250, 300, False)
    assert "Close call" in result["insights"][0]


def test_overboost_comfortable():
    result = topics.overboost(100, 100, 300, False)
    assert result["insights"] == []


def test_takeoff_map_no_data():
    result = topics.takeoff_map(None, None, None, {})
    assert result["insights"] == []


def test_takeoff_map_still_collecting():
    result = topics.takeoff_map(45.0, 1000, 20, {"n": 3, "confidence": "LOW"})
    assert "Still collecting" in result["analysis"]


def test_takeoff_map_deviation_fires_insight():
    model = {"n": 10, "confidence": "GOOD", "r_squared": 0.8,
             "coefficients": {"intercept": 40, "pressure_alt_ft": 0.0, "oat_c": 0.0}}
    result = topics.takeoff_map(45.0, 1000, 20, model)
    # expected == 40, observed == 45 -> delta 5, above threshold
    assert result["insights"]
    assert "above" in result["insights"][0]


def test_oil_temp_peak_fires_insight_once():
    # notebooks/04_flight_report.py had this loop duplicated before Stage 2
    # (every triggered insight for this topic printed twice) — fixed as
    # part of the extraction, verified against no golden report ever
    # exercising this path (none of the 6 golden flights exceed 248°F).
    b = {"mean": 200, "std": 10, "n": 20}
    rule = {"type": "threshold", "limit": 248}
    result = topics.oil_temp_peak(260, b, [rule])
    assert result["insights"] == ["⚠ Exceeded OM limit of 248°F."]


def test_oil_temp_peak_no_data():
    result = topics.oil_temp_peak(None, {"mean": None}, [])
    assert result["analysis"] == "Oil temperature data not available."
    assert result["insights"] == []


def test_coolant_temp_peak_no_duplication():
    # Unlike oil_temp_peak, this topic doesn't have the duplicate-loop bug.
    b = {"mean": 200, "std": 10, "n": 20}
    rule = {"type": "threshold", "limit": 248}
    result = topics.coolant_temp_peak(260, b, [rule])
    assert result["insights"] == ["⚠ Exceeded OM limit of 248°F."]


def test_cruise_fuel_flow_high_da_appends_note():
    b = {"mean": 6.0, "std": 0.5, "n": 20}
    rule = {"type": "baseline_deviation", "z_score_threshold": 1.0}
    result = topics.cruise_fuel_flow(
        8.0, b, [rule], this_da=12000, fleet_da_avg=5000, fleet_da_std=1000,
    )
    assert "cruise DA was" in result["insights"][0]


def test_cruise_fuel_flow_low_da_no_note():
    b = {"mean": 6.0, "std": 0.5, "n": 20}
    rule = {"type": "baseline_deviation", "z_score_threshold": 1.0}
    result = topics.cruise_fuel_flow(
        8.0, b, [rule], this_da=5000, fleet_da_avg=5000, fleet_da_std=1000,
    )
    assert "cruise DA was" not in result["insights"][0]


def test_cruise_fuel_flow_still_building():
    result = topics.cruise_fuel_flow(8.0, {"mean": None}, [])
    assert "Still building" in result["analysis"]


def test_limit_exceedances_none():
    result = topics.limit_exceedances([])
    assert result["insights"] == []
    assert "No OM" in result["analysis"]


def test_limit_exceedances_present():
    result = topics.limit_exceedances(["RPM above 5800 for 10s"])
    assert result["insights"] == ["⚠ RPM above 5800 for 10s"]


def test_engine_ecu_inflight_no_events():
    result = topics.engine_ecu_inflight([
        {"classification": "POWERUP"}, {"classification": "LANE_CHECK"},
    ])
    assert result["events"] == []
    assert "No IN-FLIGHT" in result["analysis"]


def test_engine_ecu_inflight_delegates_to_cas_analysis():
    import pandas as pd
    runs = [{
        "classification": "IN_FLIGHT",
        "source_file": "x.csv",
        "start_time": pd.Timestamp("2026-01-01 12:00:00"),
        "duration_s": 1,
        "oil_nan_frac": 0.0,
        "co_alerts": ["OIL PRESS"],
    }]
    result = topics.engine_ecu_inflight(runs)
    assert "1 IN-FLIGHT" in result["analysis"]
    assert result["events"][0]["direct_correlation_alerts"] == ["OIL PRESS"]
