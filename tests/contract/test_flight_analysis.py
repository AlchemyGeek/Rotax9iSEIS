"""
Contract tests for analyze_flight() / FlightAnalysis (Spec 01 §7, §8.3,
§11 Stage 3, §12 acceptance criteria 1, 2, 3, 5, 6).
"""
import json
from pathlib import Path

import jsonschema
import pandas as pd
import pytest

from slingology_eis.limits import load_engine_config
from slingology_eis.operations import analyze_flight

from ..conftest import GOLDEN_DIR, LOGS_DIR, requires_flight_logs, requires_golden_fixtures

_CONTRACT_ROOT = Path(__file__).resolve().parent.parent.parent / "contract"
_SCHEMA = json.loads((_CONTRACT_ROOT / "schema" / "flight_analysis.schema.json").read_text())

_META = (
    'aircraft_ident="N999XX", product="GDU 460", system_id="123456789", '
    'unit="1", airframe_hours="10.5", engine_hours="20.1", log_version="7"\n'
)
_HEADER = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Oil Temp (deg F)\n"
_ROWS = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{2000+i},180\n" for i in range(120))
_SYNTHETIC_LOG = (_META + _HEADER + _ROWS).encode("utf-8")


def _engine_config():
    return load_engine_config()


# ── Schema validation (criterion 5) — synthetic data, no private logs needed ──

def test_analyze_flight_validates_against_schema_synthetic():
    fa = analyze_flight(_SYNTHETIC_LOG, "log_20260101_120000_TEST.csv", _engine_config(), "916iS")
    jsonschema.validate(fa.to_dict(), _SCHEMA)


def test_analyze_flight_result_has_no_bare_nan():
    fa = analyze_flight(_SYNTHETIC_LOG, "log_20260101_120000_TEST.csv", _engine_config(), "916iS")
    # A bare NaN survives json.dumps as an invalid literal that json.loads
    # then rejects — round-tripping is the simplest way to prove there is
    # none, matching how the engine's own serializer (serialize.py) works.
    text = json.dumps(fa.to_dict())
    assert "NaN" not in text
    json.loads(text)  # would raise if it somehow were there


def test_analyze_flight_missing_metrics_have_a_reason():
    fa = analyze_flight(_SYNTHETIC_LOG, "log_20260101_120000_TEST.csv", _engine_config(), "916iS")
    for metric_id, mv in fa.to_dict()["metrics"].items():
        if mv["value"] is None:
            assert mv.get("missing"), f"{metric_id} is null with no missing reason"


def test_analyze_flight_no_cruise_channel_missing_distinct_reasons():
    fa = analyze_flight(_SYNTHETIC_LOG, "log_20260101_120000_TEST.csv", _engine_config(), "916iS")
    metrics = fa.to_dict()["metrics"]
    # No CRUISE phase in this synthetic log -> NO_PHASE
    assert metrics["egt_spread_mean_f"]["missing"] == "NO_PHASE"
    # baro_alt_ft channel isn't in this synthetic log's columns -> CHANNEL_MISSING
    assert metrics["max_altitude_ft"]["missing"] == "CHANNEL_MISSING"


# ── Criterion 6: no filesystem/environment/clock access in the core ──────────

def test_analyze_flight_touches_no_filesystem(monkeypatch):
    engine_config = _engine_config()  # loaded before blocking — that's host-side I/O, not the core call

    def _blocked(*args, **kwargs):
        raise AssertionError("analyze_flight must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _blocked)
    fa = analyze_flight(_SYNTHETIC_LOG, "log_20260101_120000_TEST.csv", engine_config, "916iS")
    assert fa.flight_id


def test_analyze_flight_touches_no_environment(monkeypatch):
    engine_config = _engine_config()

    def _blocked(*args, **kwargs):
        raise AssertionError("analyze_flight must not read environment variables")

    monkeypatch.setattr("os.environ.get", _blocked)
    fa = analyze_flight(_SYNTHETIC_LOG, "log_20260101_120000_TEST.csv", engine_config, "916iS")
    assert fa.flight_id


def test_analyze_flight_touches_no_wall_clock(monkeypatch):
    import datetime
    engine_config = _engine_config()

    class _BlockedDate(datetime.date):
        @classmethod
        def today(cls):
            raise AssertionError("analyze_flight must not read the wall clock")

    monkeypatch.setattr("datetime.date", _BlockedDate)
    fa = analyze_flight(_SYNTHETIC_LOG, "log_20260101_120000_TEST.csv", engine_config, "916iS")
    assert fa.flight_id


# ── Acceptance criteria 1, 2, 3 — the real KACV log, gated on private data ───

KACV_LOG = "log_20260423_200615_KACV.csv"


@requires_flight_logs
@requires_golden_fixtures
def test_analyze_flight_kacv_reproduces_fleet_metrics_csv_row():
    log_path = LOGS_DIR / KACV_LOG
    if not log_path.exists():
        pytest.skip(f"{KACV_LOG} not present locally")

    fa = analyze_flight(log_path.read_bytes(), KACV_LOG, _engine_config(), "916iS")
    metrics = fa.to_dict()["metrics"]

    fm = pd.read_csv(GOLDEN_DIR / "fleet_metrics.csv")
    match = fm[fm["source_file"] == KACV_LOG]
    if not len(match):
        pytest.skip(f"{KACV_LOG} not present in the golden fleet_metrics.csv")
    row = match.iloc[0]

    checked = 0
    for metric_id, mv in metrics.items():
        if metric_id not in row.index:
            continue
        checked += 1
        csv_val = row[metric_id]
        my_val = mv["value"]
        csv_is_null = pd.isna(csv_val)
        assert (my_val is None) == csv_is_null, f"{metric_id}: null mismatch"
        if csv_is_null:
            continue
        if isinstance(csv_val, float) or isinstance(my_val, float):
            assert abs(float(csv_val) - float(my_val)) < 1e-6, f"{metric_id}: {my_val} != {csv_val}"
        else:
            assert str(csv_val) == str(my_val), f"{metric_id}: {my_val} != {csv_val}"
    assert checked >= 30  # sanity: we actually compared something

    # Acceptance criterion 1's specific expected missing reasons
    assert metrics["takeoff_map_inhg"]["missing"] == "NO_PHASE"
    assert metrics["takeoff_pressure_alt_ft"]["missing"] == "NO_PHASE"
    assert metrics["takeoff_oat_c"]["missing"] == "NO_PHASE"
    assert metrics["cruise_nmpg"]["missing"] == "NO_PHASE"


@requires_flight_logs
def test_analyze_flight_kacv_emits_phase_diagnostics():
    log_path = LOGS_DIR / KACV_LOG
    if not log_path.exists():
        pytest.skip(f"{KACV_LOG} not present locally")

    fa = analyze_flight(log_path.read_bytes(), KACV_LOG, _engine_config(), "916iS")
    codes = {d["code"] for d in fa.to_dict()["quality"]}
    assert "PHASE_TAKEOFF_NOT_DETECTED" in codes
    assert "PHASE_NO_CRUISE" in codes


@requires_flight_logs
def test_analyze_flight_kacv_ecu_runs_match_golden_classification():
    log_path = LOGS_DIR / KACV_LOG
    if not log_path.exists():
        pytest.skip(f"{KACV_LOG} not present locally")

    fa = analyze_flight(log_path.read_bytes(), KACV_LOG, _engine_config(), "916iS")
    runs = fa.to_dict()["ecu_runs"]
    from collections import Counter
    counts = Counter(r["classification"] for r in runs)
    assert counts == {"POWERUP": 2, "LANE_CHECK": 2, "SHUTDOWN": 1}


@requires_flight_logs
def test_analyze_flight_kacv_validates_against_schema():
    log_path = LOGS_DIR / KACV_LOG
    if not log_path.exists():
        pytest.skip(f"{KACV_LOG} not present locally")

    fa = analyze_flight(log_path.read_bytes(), KACV_LOG, _engine_config(), "916iS")
    jsonschema.validate(fa.to_dict(), _SCHEMA)
