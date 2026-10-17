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
@pytest.mark.parametrize("log,start", [
    ("log_20260604_210855_KAWO.csv", "21:17:17"),   # engine cut, log ends (v0.20 correction)
    ("log_20260417_112526_KTOA.csv", "12:13:55"),   # engine cut while still labelled LANDING_ROLL
    ("log_20260422_183751_KTOA.csv", "19:08:23"),   # engine cut while still labelled LANDING_ROLL
    ("log_20260617_143425_KAWO.csv", "17:25:09"),   # engine cut while still labelled DESCENT at 0 kt
])
def test_criterion_3_late_phase_and_log_end_shutdowns(log, start):
    """Spec 01 §12 criterion 3 (v0.20), rule 1: these are GROUND_SHUTDOWN."""
    fa = _analyze_log(log)
    run = next(r for r in fa.ecu_runs if r["start_utc"].endswith(start))
    assert run["classification"] == "GROUND_SHUTDOWN"


@requires_flight_logs
def test_criterion_3_no_in_flight_run_on_any_log():
    """Spec 01 §12 criterion 3: IN_FLIGHT = 0 on every log the loader can
    read, ground sessions included — not just the deduplicated flights."""
    logs = sorted(LOGS_DIR.glob("*.csv"))
    if not logs:
        pytest.skip("no local flight logs")
    cfg = load_engine_config("916iS")
    in_flight, readable = [], 0
    for p in logs:
        try:
            fa = analyze_flight(p.read_bytes(), p.name, cfg, "916iS")
        except ValueError as e:
            if "unrecognised header format" in str(e):
                continue   # a format the loader can't read (shown Unreadable in the app)
            raise
        readable += 1
        in_flight += [(p.name, r["start_utc"]) for r in fa.ecu_runs if r["classification"] == "IN_FLIGHT"]
    assert readable >= 100
    assert in_flight == []


@requires_flight_logs
def test_every_ground_and_in_flight_run_is_an_event(real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    d = analyze_ecu(real_flight_analyses).to_dict()
    expected = [(r["flight_id"], r["start_utc"]) for r in d["runs"] if r["classification"] in ("GROUND", "IN_FLIGHT")]
    assert [(e["flight_id"], e["start_utc"]) for e in d["events"]] == expected
    assert d["counts"] == dict(Counter({**_ZERO, **Counter(r["classification"] for r in d["runs"])}))
