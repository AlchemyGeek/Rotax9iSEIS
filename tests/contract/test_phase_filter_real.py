"""
Spec 09 v0.20 acceptance 24 — a phase-only filter on real data: rpm_idle_min
excluding TAXI and LANDING_ROLL suppresses every event lying wholly within
those phases, leaves every other event visible, and changes no other limit
and no other topic, flight by flight.
"""
import pytest

from slingology_eis.filters import event_phases
from slingology_eis.operations import evaluate_insights

from ..conftest import requires_flight_logs

EXCLUDED = {"TAXI", "LANDING_ROLL"}
FILTER = {
    "id": "flt_idle_ground", "target": {"kind": "limit", "limit_id": "rpm_idle_min"}, "phases": sorted(EXCLUDED),
    "note": "", "reference": {"flight_ids": []}, "created_at": "2026-10-15T00:00:00Z", "history": [],
}


def _without_idle(iset: dict) -> dict:
    """Everything an insight set says, minus rpm_idle_min's own insights
    and the limit_exceedances analysis line (its "within your filters"
    count is meant to change)."""
    out = {}
    for t in iset["topics"]:
        insights = [i for i in t["insights"] if i.get("limit_id") != "rpm_idle_min"]
        body = {"insights": insights, "limit_refs": t.get("limit_refs")}
        if t["topic_id"] != "limit_exceedances":
            body["analysis"] = t["analysis"]
        out[t["topic_id"]] = body
    return out


@requires_flight_logs
def test_acceptance_24_idle_minimum_excluding_ground_phases(real_flight_analyses, real_fleet_analysis, rules):
    if not real_flight_analyses:
        pytest.skip("no local flight logs")
    suppressed = visible = 0
    for fa in real_flight_analyses:
        plain = evaluate_insights(fa, real_fleet_analysis, rules, filters=[]).to_dict()
        filtered = evaluate_insights(fa, real_fleet_analysis, rules, filters=[FILTER]).to_dict()

        assert _without_idle(filtered) == _without_idle(plain), fa.flight_id

        idle = [e for e in fa.exceedances if e.get("limit_id") == "rpm_idle_min"]
        got = {e["event_id"]: e for t in filtered["topics"] if t["topic_id"] == "limit_exceedances"
               for i in t["insights"] if i.get("limit_id") == "rpm_idle_min" for e in i["events"]}
        assert set(got) == {e["event_id"] for e in idle}, fa.flight_id
        for e in idle:
            phases = event_phases(e, fa.phases)
            expected = "phase" if set(phases) <= EXCLUDED else None
            assert got[e["event_id"]]["suppressed_by"] == expected, (fa.flight_id, e["event_id"], phases)
            assert got[e["event_id"]]["phases"] == phases
            suppressed += expected == "phase"
            visible += expected is None
    assert suppressed > 0 and visible > 0
