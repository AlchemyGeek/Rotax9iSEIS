"""
Contract tests for analyze_ecu() / EcuAnalysis (Spec 01 §7, §8.6, §12
acceptance criteria 3, 5).
"""
import json

import jsonschema
import pytest

from slingology_eis.operations import analyze_ecu

from ..conftest import requires_flight_logs, requires_golden_fixtures
from .conftest import load_schema

_SCHEMA = load_schema("ecu_analysis.schema.json")


def test_analyze_ecu_empty_input():
    ea = analyze_ecu([])
    d = ea.to_dict()
    assert d["flight_ids"] == []
    assert d["runs"] == []
    assert d["counts"] == {}
    assert d["inflight_pattern"]["events"] == []
    jsonschema.validate(d, _SCHEMA)


@requires_flight_logs
def test_analyze_ecu_validates_against_schema(real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    ea = analyze_ecu(real_flight_analyses)
    jsonschema.validate(ea.to_dict(), _SCHEMA)


@requires_flight_logs
@requires_golden_fixtures
def test_analyze_ecu_kacv_classification_matches_golden(real_flight_analyses):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    kacv = [fa for fa in real_flight_analyses if fa.header.get("airport_hint") == "KACV"]
    if not kacv:
        pytest.skip("KACV flight not present")
    ea = analyze_ecu(kacv)
    from collections import Counter
    counts = Counter(r["classification"] for r in ea.to_dict()["runs"])
    assert dict(counts) == {"POWERUP": 2, "LANE_CHECK": 2, "SHUTDOWN": 1}


@requires_flight_logs
def test_analyze_ecu_ksff_kawo_inflight_pattern(real_flight_analyses):
    """The two real IN_FLIGHT events in the local dataset: KSFF (OIL PRESS
    co-alert, direct correlation) and a 2026-08-10 KAWO (no direct
    correlation) — the same pair characterized throughout Stage 0-2."""
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    ksff = [fa for fa in real_flight_analyses if fa.header.get("airport_hint") == "KSFF"]
    kawo_0810 = [fa for fa in real_flight_analyses if fa.header.get("date") == "2026-08-10"]
    if not (ksff and kawo_0810):
        pytest.skip("KSFF/2026-08-10 KAWO flight not present")

    ea = analyze_ecu(ksff + kawo_0810)
    d = ea.to_dict()
    assert d["counts"].get("IN_FLIGHT") == 2
    direct_correlation_events = [e for e in d["inflight_pattern"]["events"] if e["direct_correlation_alerts"]]
    assert len(direct_correlation_events) == 1
    assert direct_correlation_events[0]["direct_correlation_alerts"] == ["OIL PRESS"]


def test_analyze_ecu_no_bare_nan():
    ea = analyze_ecu([])
    text = json.dumps(ea.to_dict())
    assert "NaN" not in text
    json.loads(text)
