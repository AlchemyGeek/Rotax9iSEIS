"""
Spec 16 acceptance 7 on the private log set: the scan emits the
full-power rpm cycle as a *recurring pattern* candidate at *normal*
sensitivity; resolving it *nothing-here* keeps it out until the recent
window has moved on by half its flights. (The nominal-synthetic clause is
tests/unit/test_investigations_ops.py.) Only aggregate facts are asserted.
"""
import pytest

from ..conftest import LOGS_DIR, requires_flight_logs
from .test_research_acceptance import INVESTIGATION_THROUGH, _Host

pytestmark = requires_flight_logs


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    h = _Host(tmp_path_factory.mktemp("inbox-home"))
    h.workspace("Inbox acceptance", LOGS_DIR.resolve())
    return h


def _recurring(listing):
    return [c for c in listing["candidates"] if c["kind"] == "recurring"]


def test_7_full_power_cycle_is_a_recurring_candidate_at_normal(app):
    got = app.call("inbox_scan", as_of=INVESTIGATION_THROUGH)
    rec = _recurring(got)
    fp = [c for c in rec if c["preset"] == "full_power" and c["descriptors"] == ["rpm.period"]]
    assert len(fp) == 1, [(c["preset"], c["descriptors"]) for c in rec]
    c = fp[0]
    assert c["status"] == "new" and c["sensitivity"] == "normal"
    assert c["parameters"]["n"] == 6 and c["parameters"]["m"] == 10
    assert c["fired"]["hits"] >= 6 and c["fired"]["of"] == 10
    assert len(c["slices"]) == 10 and c["evidence"]["rows"]
    assert "governor holds rpm" in c["summary"]


def test_7_quiet_and_curious_agree_on_the_cycle(app):
    for level in ("quiet", "curious"):
        app.call("save_workspace_settings", settings={"research_sensitivity": level})
        got = app.call("inbox_scan", as_of=INVESTIGATION_THROUGH)
        assert any(c["preset"] == "full_power" and c["descriptors"] == ["rpm.period"] for c in _recurring(got)), level
    app.call("save_workspace_settings", settings={"research_sensitivity": "normal"})


def test_7_nothing_here_keeps_it_out_until_the_window_moves(app):
    early = "2026-08-31"
    got = app.call("inbox_scan", as_of=early)
    c = next(c for c in _recurring(got) if c["preset"] == "full_power" and c["descriptors"] == ["rpm.period"])
    app.call("inbox_resolve", candidate_id=c["id"], status="nothing-here", note="governor hunting")
    # The same window, scanned again: it stays resolved, no new candidate.
    again = app.call("inbox_scan", as_of=early)
    fp = [x for x in _recurring(again) if x["preset"] == "full_power" and x["descriptors"] == ["rpm.period"]]
    assert [x["status"] for x in fp] == ["nothing-here"]
    # Two months on, the recent window holds none of those flights: it comes back.
    later = app.call("inbox_scan", as_of=INVESTIGATION_THROUGH)
    fp = [x for x in _recurring(later) if x["preset"] == "full_power" and x["descriptors"] == ["rpm.period"]]
    assert sorted(x["status"] for x in fp) == ["new", "nothing-here"]
    new = next(x for x in fp if x["status"] == "new")
    assert not set(new["window"]["flight_ids"]) & set(c["window"]["flight_ids"])
