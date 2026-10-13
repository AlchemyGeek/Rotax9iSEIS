"""
Unit tests for ENGINE ECU run extraction and classification (cas.py,
Spec 01 §8.6 v0.19). Synthetic data, plus the Spec 01 Q6 excerpts in
tests/fixtures/ecu/ — short windows of real logs, scrubbed to engine
channels, CAS and the phase label on a fixed fake date (no tail number,
GPS, airport or real time).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from slingology_eis.cas import ECU_CLASSES, TAXI_IAS_CEILING_KT, ecu_active_series, extract_engine_ecu_runs
from slingology_eis.limits import load_engine_config

EXCERPTS = Path(__file__).resolve().parent.parent / "fixtures" / "ecu"
CFG = {"cas": {"merge_gap_s": 5, "min_event_duration_s": 3},
       "phase_detection": {"runup_rpm_min": 3000, "runup_rpm_max": 5000, "lane_check_max_duration_s": 15}}


def _flight(segments, ecu=()):
    """segments: [(phase, rows, rpm, ias_kt, gnd_spd_kt)], 1 Hz. `ecu`: row
    ranges (start, stop) with ENGINE ECU active."""
    rows = []
    for phase, n, rpm, ias, gs in segments:
        rows += [{"phase": phase, "rpm": rpm, "ias_kt": ias, "gnd_spd_kt": gs}] * n
    df = pd.DataFrame(rows)
    df["datetime"] = pd.date_range("2000-01-01", periods=len(df), freq="s")
    df["_source_file"] = "synthetic.csv"
    active = np.zeros(len(df), dtype=bool)
    for a, b in ecu:
        active[a:b] = True
    df["cas_alert"] = np.where(active, "ENGINE ECU", "")
    return df


def _classes(ext):
    return [(r["classification"], r["phase"]) for r in ext.runs]


def test_ecu_active_series_detects_engine_ecu_token():
    df = pd.DataFrame({"cas_alert": ["ENGINE ECU", "FUEL PRESS", "ENGINE ECU / OIL PRESS", None, ""]})
    assert list(ecu_active_series(df)) == [True, False, True, False, False]


# ── Run extraction ────────────────────────────────────────────────────────────

def test_runs_shorter_than_min_duration_are_blips_not_runs():
    df = _flight([("TAXI", 60, 1800, 5, 5)], ecu=[(10, 12), (30, 33)])  # 2 s, then 3 s
    ext = extract_engine_ecu_runs(df, CFG)
    assert ext.sub_threshold_blips == 1
    assert [r["duration_s"] for r in ext.runs] == [3]


def test_runs_closer_than_merge_gap_merge_into_one():
    # Rows 10–11 on, 12–14 off, 15–16 on: separation (next start − previous
    # end) 4 s < 5 s → one run spanning 7 s; two 2 s blips otherwise.
    df = _flight([("TAXI", 60, 1800, 5, 5)], ecu=[(10, 12), (15, 17)])
    ext = extract_engine_ecu_runs(df, CFG)
    assert ext.sub_threshold_blips == 0
    assert [(r["duration_s"], r["start_idx"], r["end_idx"]) for r in ext.runs] == [(7, 10, 16)]


def test_runs_at_merge_gap_stay_separate():
    df = _flight([("TAXI", 60, 1800, 5, 5)], ecu=[(10, 13), (18, 21)])  # separation exactly 5 s
    assert len(extract_engine_ecu_runs(df, CFG).runs) == 2


def test_merge_gap_and_min_duration_come_from_the_profile():
    df = _flight([("TAXI", 60, 1800, 5, 5)], ecu=[(10, 12)])
    assert extract_engine_ecu_runs(df, {**CFG, "cas": {"merge_gap_s": 5, "min_event_duration_s": 2}}).runs
    for engine in ("912iS", "914iS", "915iS", "916iS"):
        assert set(load_engine_config(engine)["cas"]) == {"merge_gap_s", "min_event_duration_s"}


# ── Classification by phase ───────────────────────────────────────────────────

@pytest.mark.parametrize("phase,expected", [
    ("PRE_START", "GROUND_START"), ("ENGINE_START", "GROUND_START"), ("WARMUP", "GROUND_START"),
    ("TAXI", "GROUND"),
    ("TAKEOFF_ROLL", "IN_FLIGHT"), ("CLIMB", "IN_FLIGHT"), ("CRUISE", "IN_FLIGHT"),
    ("DESCENT", "IN_FLIGHT"), ("APPROACH", "IN_FLIGHT"), ("LANDING_ROLL", "IN_FLIGHT"),
    ("SHUTDOWN", "GROUND_SHUTDOWN"),
])
def test_each_phase_maps_to_its_class(phase, expected):
    df = _flight([(phase, 30, 2000, 60, 60)], ecu=[(5, 15)])
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [(expected, phase)]


def test_landing_roll_below_5_kt_ground_speed_is_ground():
    df = _flight([("LANDING_ROLL", 30, 1800, 10, 3)], ecu=[(5, 15)])
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [("GROUND", "LANDING_ROLL")]


def test_majority_phase_decides_a_run_spanning_phases():
    # 6 rows WARMUP (GROUND_START) + 4 rows TAXI (GROUND) → GROUND_START.
    df = _flight([("WARMUP", 20, 1800, 0, 0), ("TAXI", 20, 1800, 5, 5)], ecu=[(14, 24)])
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [("GROUND_START", "WARMUP")]


def test_in_flight_wins_when_overlap_reaches_min_duration():
    # 3 of 10 rows in TAKEOFF_ROLL — a minority, but ≥ min_event_duration_s.
    df = _flight([("TAXI", 20, 2000, 10, 10), ("TAKEOFF_ROLL", 20, 5700, 40, 40)], ecu=[(13, 23)])
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [("IN_FLIGHT", "TAKEOFF_ROLL")]


def test_in_flight_overlap_below_min_duration_does_not_win():
    df = _flight([("TAXI", 20, 2000, 10, 10), ("TAKEOFF_ROLL", 20, 5700, 40, 40)], ecu=[(12, 22)])  # 2 rows
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [("GROUND", "TAXI")]


def test_unknown_phase_takes_nearest_preceding_known_phase_and_is_uncertain():
    df = _flight([("TAXI", 20, 1800, 5, 5), ("UNKNOWN", 20, 1800, 5, 5)], ecu=[(25, 30)])
    ext = extract_engine_ecu_runs(df, CFG)
    assert _classes(ext) == [("GROUND", "TAXI")]
    assert ext.runs[0]["phase_uncertain"] is True


def test_old_heuristics_are_gone_engine_off_in_taxi_is_still_ground():
    # The old classifier called any run with < 30 % rpm > 500 "start-up";
    # phase alone decides now.
    df = _flight([("TAXI", 30, 0, 0, 0)], ecu=[(5, 15)])
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [("GROUND", "TAXI")]


# ── Finding-9 guard ───────────────────────────────────────────────────────────

def test_finding_9_guard_turns_a_fast_ground_run_in_flight_when_takeoff_was_missed():
    fast = TAXI_IAS_CEILING_KT + 20
    df = _flight([("TAXI", 30, 5000, fast, fast)], ecu=[(5, 15)])
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [("GROUND", "TAXI")]
    ext = extract_engine_ecu_runs(df, CFG, takeoff_not_detected=True)
    assert _classes(ext) == [("IN_FLIGHT", "TAXI")]
    assert ext.runs[0]["phase_uncertain"] is True


def test_finding_9_guard_leaves_a_slow_ground_run_alone():
    df = _flight([("TAXI", 30, 1800, 10, 10)], ecu=[(5, 15)])
    ext = extract_engine_ecu_runs(df, CFG, takeoff_not_detected=True)
    assert _classes(ext) == [("GROUND", "TAXI")]
    assert ext.runs[0]["phase_uncertain"] is False


# ── Lane check ────────────────────────────────────────────────────────────────

def _lane_check_flight(n_checks):
    ecu = [(10, 15), (25, 30)][:n_checks]
    return _flight([("TAXI", 60, 4000, 5, 0)], ecu=ecu)


@pytest.mark.parametrize("n_checks,expected", [(2, "both"), (1, "single"), (0, "none")])
def test_lane_check_value(n_checks, expected):
    ext = extract_engine_ecu_runs(_lane_check_flight(n_checks), CFG)
    assert ext.lane_check == expected
    assert all(r["classification"] == "LANE_CHECK" for r in ext.runs)
    assert all(r["lane_check_pair"] == (expected == "both") for r in ext.runs)


def test_run_up_outside_the_lane_check_signature_is_ground():
    df = _flight([("TAXI", 60, 2500, 5, 0)], ecu=[(10, 15)])  # below run-up band
    assert _classes(extract_engine_ecu_runs(df, CFG)) == [("GROUND", "TAXI")]


# ── Context means ─────────────────────────────────────────────────────────────

def test_context_means_skip_nan():
    df = _flight([("CRUISE", 20, 4000, 90, 90)], ecu=[(0, 20)])
    df["oil_press_psi"] = [2.0] * 19 + [np.nan]
    df["main_volts"] = 13.0
    r = extract_engine_ecu_runs(df, CFG).runs[0]
    # skipna mean: a data gap mustn't drag a healthy reading toward the
    # near-zero signature a co-alert check looks for.
    assert r["mean_oil_press_psi"] == 2.0
    assert r["mean_main_volts"] == 13.0
    assert round(r["oil_nan_frac"], 4) == round(1 / 20, 4)
    assert r["mean_coolant_temp_f"] is None


# ── Spec 01 Q6 excerpts (scrubbed real data) ──────────────────────────────────

def _excerpt(name):
    return pd.read_csv(EXCERPTS / f"{name}.csv", parse_dates=["datetime"])


def test_excerpt_engine_catch_blip_is_sub_threshold_only():
    ext = extract_engine_ecu_runs(_excerpt("engine_catch_blip_0527"), load_engine_config("916iS"))
    assert ext.runs == [] and ext.sub_threshold_blips == 1


def test_excerpt_paired_lane_check():
    ext = extract_engine_ecu_runs(_excerpt("lane_check_pair"), load_engine_config("916iS"))
    assert [r["classification"] for r in ext.runs] == ["LANE_CHECK", "LANE_CHECK"]
    assert ext.lane_check == "both"


def test_excerpt_ground_taxi_run():
    ext = extract_engine_ecu_runs(_excerpt("ground_taxi_run"), load_engine_config("916iS"))
    assert _classes(ext) == [("GROUND", "TAXI"), ("GROUND", "TAXI")]


def test_excerpt_0604_run_ends_at_shutdown():
    """Spec 01 v0.19 reads this 5 s run (non-zero oil_nan_frac) as a GROUND
    CAN dropout at idle. The phase detector puts 3 of its 5 rows in
    SHUTDOWN — rpm and oil pressure both stop and the log ends — so the
    majority rule makes it GROUND_SHUTDOWN. Recorded as found, not tuned."""
    ext = extract_engine_ecu_runs(_excerpt("ground_start_shutdown_0604"), load_engine_config("916iS"))
    assert _classes(ext) == [("GROUND_SHUTDOWN", "SHUTDOWN")]
    assert ext.runs[0]["duration_s"] == 5 and ext.runs[0]["oil_nan_frac"] > 0


def test_ecu_classes_are_the_five():
    assert ECU_CLASSES == ("GROUND_START", "LANE_CHECK", "GROUND", "IN_FLIGHT", "GROUND_SHUTDOWN")
