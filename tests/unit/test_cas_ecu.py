"""
Unit tests for the Stage 2a ECU pattern-analysis functions in cas.py.
Synthetic data only.
"""
import pandas as pd

from slingology_eis.cas import (
    DIRECT_CORRELATION_ALERTS,
    RECOMMENDED_ACTIONS_ENGINE_ECU_INFLIGHT,
    analyze_inflight_pattern,
    classify_coactive_alerts,
    ecu_active_series,
)


def test_ecu_active_series_detects_engine_ecu_token():
    df = pd.DataFrame({"cas_alert": ["ENGINE ECU", "FUEL PRESS", "ENGINE ECU / OIL PRESS", None, ""]})
    result = list(ecu_active_series(df))
    assert result == [True, False, True, False, False]


def test_classify_coactive_alerts_splits_and_preserves_order():
    result = classify_coactive_alerts(["FUEL PRESS", "OIL PRESS", "RAGL FAIL"])
    assert result == {
        "direct_correlation": ["OIL PRESS"],
        "other": ["FUEL PRESS", "RAGL FAIL"],
    }


def test_classify_coactive_alerts_empty():
    assert classify_coactive_alerts([]) == {"direct_correlation": [], "other": []}


def _run(source_file, duration_s, oil_nan_frac, co_alerts):
    return {
        "source_file": source_file,
        "start_time": pd.Timestamp("2026-01-01 12:00:00"),
        "duration_s": duration_s,
        "oil_nan_frac": oil_nan_frac,
        "co_alerts": co_alerts,
    }


def test_analyze_inflight_pattern_empty():
    result = analyze_inflight_pattern([])
    assert result["events"] == []
    assert result["oil_nan_pattern"] is None
    assert result["recommended_actions"] == RECOMMENDED_ACTIONS_ENGINE_ECU_INFLIGHT


def test_analyze_inflight_pattern_strong_oil_nan_correlation():
    runs = [
        _run("a.csv", 1, 0.9, ["OIL PRESS", "FUEL PRESS"]),
        _run("b.csv", 2, 0.95, []),
    ]
    result = analyze_inflight_pattern(runs)
    assert result["oil_nan_pattern"] == "strong"
    assert len(result["events"]) == 2
    assert result["events"][0]["direct_correlation_alerts"] == ["OIL PRESS"]
    assert result["events"][1]["direct_correlation_alerts"] == []
    # recommended_actions is a fresh copy each call, not the same list object
    assert result["recommended_actions"] == RECOMMENDED_ACTIONS_ENGINE_ECU_INFLIGHT
    assert result["recommended_actions"] is not RECOMMENDED_ACTIONS_ENGINE_ECU_INFLIGHT


def test_analyze_inflight_pattern_mixed_when_below_threshold():
    # 1 of 3 events strong (33%) -> not > 60% -> "mixed"
    runs = [
        _run("a.csv", 1, 0.9, []),
        _run("b.csv", 1, 0.1, []),
        _run("c.csv", 1, None, []),
    ]
    result = analyze_inflight_pattern(runs)
    assert result["oil_nan_pattern"] == "mixed"


def test_analyze_inflight_pattern_none_oil_nan_frac_treated_as_not_strong():
    runs = [_run("a.csv", 1, None, [])]
    result = analyze_inflight_pattern(runs)
    assert result["oil_nan_pattern"] == "mixed"
    assert result["events"][0]["oil_nan_frac"] is None
