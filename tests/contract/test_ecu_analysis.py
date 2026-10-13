"""
Contract tests for analyze_ecu() / EcuAnalysis (Spec 01 §7, §8.6 v0.19,
§12 acceptance criteria 3, 5).
"""
import json
from collections import Counter

import jsonschema
import pytest

from slingology_eis.limits import load_engine_config
from slingology_eis.operations import analyze_ecu, analyze_flight

from ..conftest import LOGS_DIR, requires_flight_logs
from .conftest import load_schema

_SCHEMA = load_schema("ecu_analysis.schema.json")
_ZERO = {"GROUND_START": 0, "LANE_CHECK": 0, "GROUND": 0, "IN_FLIGHT": 0, "GROUND_SHUTDOWN": 0}


def _analyze_log(name: str):
    path = LOGS_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not present locally")
    return analyze_flight(path.read_bytes(), name, load_engine_config("916iS"), "916iS")


def test_analyze_ecu_empty_input():
    d = analyze_ecu([]).to_dict()
    assert d["flight_ids"] == [] and d["runs"] == [] and d["flights"] == [] and d["events"] == []
    assert d["counts"] == _ZERO
    assert d["sub_threshold_blips"] == 0
    assert "inflight_pattern" not in d
    jsonschema.validate(d, _SCHEMA)


def test_analyze_ecu_no_bare_nan():
    text = json.dumps(analyze_ecu([]).to_dict())
    assert "NaN" not in text
    json.loads(text)


@requires_flight_logs
def test_analyze_ecu_validates_against_schema(real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    jsonschema.validate(analyze_ecu(real_flight_analyses).to_dict(), _SCHEMA)


@requires_flight_logs
def test_criterion_3_kacv_classes_and_lane_check():
    """Spec 01 §12 criterion 3: 2 GROUND_START, 2 LANE_CHECK, 1
    GROUND_SHUTDOWN, lane_check "both", no GROUND, no IN_FLIGHT."""
    d = analyze_ecu([_analyze_log("log_20260423_200615_KACV.csv")]).to_dict()
    assert d["counts"] == {**_ZERO, "GROUND_START": 2, "LANE_CHECK": 2, "GROUND_SHUTDOWN": 1}
    assert d["flights"][0]["lane_check"] == "both"
    assert d["events"] == []


@requires_flight_logs
@pytest.mark.parametrize("log,start", [
    ("log_20260423_194224_KACV.csv", "19:44:50"),
    ("log_20260430_182054_KAWO.csv", "18:30:26"),
    ("log_20260527_200344_KSFF.csv", "20:06:38"),
])
def test_criterion_3_named_blips_are_sub_threshold_only(log, start):
    fa = _analyze_log(log)
    assert not any((r["start_utc"] or "").endswith(start) for r in fa.ecu_runs)
    assert fa.ecu_sub_threshold_blips >= 1


@requires_flight_logs
@pytest.mark.xfail(strict=True, reason=(
    "Spec 01 v0.19 reads 2026-06-04 21:17:17 as a GROUND CAN dropout; the phase "
    "detector puts 3 of its 5 rows in SHUTDOWN (rpm and oil pressure stop, the "
    "log ends), so the majority rule makes it GROUND_SHUTDOWN. Reported, not tuned."))
def test_criterion_3_0604_run_is_ground():
    fa = _analyze_log("log_20260604_210855_KAWO.csv")
    run = next(r for r in fa.ecu_runs if r["start_utc"].endswith("21:17:17"))
    assert run["classification"] == "GROUND"


@requires_flight_logs
@pytest.mark.xfail(strict=True, reason=(
    "Three shutdown runs (2026-04-17, 2026-04-22, 2026-06-17) start in the last "
    "4-11 rows the phase detector still labels LANDING_ROLL (taxiing at 7-9 kt) "
    "or DESCENT (0 kt) before SHUTDOWN; ≥ min_event_duration_s of in-flight "
    "phase makes them IN_FLIGHT under §8.6's rule. Reported, not tuned."))
def test_criterion_3_no_in_flight_runs_on_any_flight(real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    flights = analyze_ecu(real_flight_analyses).to_dict()["flights"]
    assert [f["flight_id"] for f in flights if f["counts"]["IN_FLIGHT"]] == []


@requires_flight_logs
def test_every_ground_and_in_flight_run_is_an_event(real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    d = analyze_ecu(real_flight_analyses).to_dict()
    expected = [(r["flight_id"], r["start_utc"]) for r in d["runs"] if r["classification"] in ("GROUND", "IN_FLIGHT")]
    assert [(e["flight_id"], e["start_utc"]) for e in d["events"]] == expected
    assert d["counts"] == dict(Counter({**_ZERO, **Counter(r["classification"] for r in d["runs"])}))
