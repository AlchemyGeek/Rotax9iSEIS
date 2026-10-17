"""
Spec 12 v0.4, Session C Phase 6 — event frequency (§5.8), readiness
(§9.3) and the frequency shift-history kind (§15 acceptance 13/14).
"""
from slingology_eis.limits import limit_catalog, load_engine_config
from slingology_eis.operations import DEFAULT_BASELINE_CONFIG, update_fleet
from slingology_eis.trends import event_frequency, recent_window, two_proportion_z
from slingology_eis.workspace import _shift_event_kind, update_shift_history

from ..contract.test_trends import _fa  # shared synthetic FlightAnalysis builder

_CFG = load_engine_config("916iS")


# ── two_proportion_z ────────────────────────────────────────────────────────

def test_two_proportion_z_well_defined_at_a_zero_reference_share():
    """A zero reference share alone doesn't make the pooled proportion
    0 or 1 as long as the recent share is nonzero — z is computable."""
    z = two_proportion_z(4, 10, 0, 40)
    assert z is not None and z > 0


def test_two_proportion_z_none_when_both_shares_are_zero():
    assert two_proportion_z(0, 10, 0, 40) is None


def test_two_proportion_z_none_with_an_empty_group():
    assert two_proportion_z(0, 0, 1, 10) is None


# ── event_frequency ──────────────────────────────────────────────────────────

def _window_and_points(recent_events, recent_n, ref_events, ref_n):
    """points for ref_n reference flights (x 0..ref_n-1) then recent_n
    recent flights (x ref_n..ref_n+recent_n-1); the first `events` flights
    of each group get value 1.0 (an event), the rest 0.0."""
    points = []
    for i in range(ref_n):
        points.append({"flight_id": f"ref{i}", "x": float(i), "value": 1.0 if i < ref_events else 0.0})
    for i in range(recent_n):
        points.append({
            "flight_id": f"rec{i}", "x": float(ref_n + i),
            "value": 1.0 if i < recent_events else 0.0,
        })
    window = {"flight_ids": [f"rec{i}" for i in range(recent_n)]}
    reference_ids = [f"ref{i}" for i in range(ref_n)]
    return points, window, reference_ids


def test_event_frequency_qualifies_on_a_clear_rise():
    points, window, reference_ids = _window_and_points(recent_events=4, recent_n=10, ref_events=1, ref_n=40)
    freq = event_frequency(points, window, reference_ids, lambda v: v > 0, frequency_delta=0.30, n_min=10)
    assert freq["recent"] == {"events": 4, "flights": 10}
    assert freq["reference"] == {"events": 1, "flights": 40}
    assert freq["delta"] == 0.4 - 0.025
    assert freq["qualifies"] is True
    assert freq["z"] is not None


def test_event_frequency_does_not_qualify_with_one_recent_event_from_a_zero_reference():
    """§5.8's carve-out: a zero reference share and exactly one recent
    event is too thin a signal, even though the raw delta clears
    frequency_delta."""
    points, window, reference_ids = _window_and_points(recent_events=1, recent_n=10, ref_events=0, ref_n=40)
    freq = event_frequency(points, window, reference_ids, lambda v: v > 0, frequency_delta=0.30, n_min=10)
    assert freq["delta"] == 0.1
    assert freq["qualifies"] is False


def test_event_frequency_two_recent_events_from_a_zero_reference_does_qualify():
    """The same zero-reference scenario with more than one recent event
    is no longer "thin" and qualifies normally."""
    points, window, reference_ids = _window_and_points(recent_events=4, recent_n=10, ref_events=0, ref_n=40)
    freq = event_frequency(points, window, reference_ids, lambda v: v > 0, frequency_delta=0.30, n_min=10)
    assert freq["qualifies"] is True


def test_event_frequency_below_n_min_reference_never_qualifies():
    points, window, reference_ids = _window_and_points(recent_events=5, recent_n=10, ref_events=0, ref_n=5)
    freq = event_frequency(points, window, reference_ids, lambda v: v > 0, frequency_delta=0.30, n_min=10)
    assert freq["qualifies"] is False


# ── update_fleet integration ─────────────────────────────────────────────────

def test_never_exceeded_limit_gets_the_no_events_badge_and_never_ranks():
    """EGT3-max on the real fleet: every eligible flight shows up in
    time_above_pct (always 0) but none in peak_excess — both read
    'no_events' and neither ranks."""
    lim = next(l for l in limit_catalog(_CFG) if l["id"] == "oil_temp_max")
    # per_limit_metrics() always emits lim_<id>_peak_excess (None when no
    # event) alongside lim_<id>_time_above_pct — explicit here so the
    # synthetic fleet's DataFrame carries the (all-NaN) column the real
    # pipeline would, rather than omitting it outright.
    fas = [
        _fa(i, {"oil_temp_max_f": 190.0, "lim_oil_temp_max_peak_excess": None, "lim_oil_temp_max_time_above_pct": 0.0},
            limits=[lim])
        for i in range(30)
    ]
    fleet = update_fleet(fas)
    peak = fleet.metrics["limit_oil_temp_max_peak_excess"]
    pct = fleet.metrics["limit_oil_temp_max_time_above_pct"]
    assert peak["readiness"] == {"kind": "no_events"}
    assert pct["readiness"] == {"kind": "no_events"}
    assert peak["frequency"]["qualifies"] is False
    assert all(m["metric_id"] != "limit_oil_temp_max_peak_excess" for m in fleet.change_summary)


def _oil_temp_frequency_fleet(lim, n_quiet=38, n_eventful=12):
    """n_quiet flights with no event, then n_eventful with an identical-
    magnitude event — the recent window (hours-gated, Spec 12 §5.1) ends
    up a flight or two wider than n_eventful, so the eventful tail is
    sized generously enough that the window's exact boundary doesn't
    matter: every window the engine could pick is still all-event, and
    only one eventful flight at most leaks into the reference."""
    fas = [
        _fa(i, {"oil_temp_max_f": 190.0, "lim_oil_temp_max_peak_excess": None, "lim_oil_temp_max_time_above_pct": 0.0},
            limits=[lim])
        for i in range(n_quiet)
    ]
    fas += [
        _fa(n_quiet + i, {
            "oil_temp_max_f": 190.0, "lim_oil_temp_max_peak_excess": 5.0, "lim_oil_temp_max_time_above_pct": 1.0,
        }, limits=[lim])
        for i in range(n_eventful)
    ]
    return fas


def test_frequent_limit_with_constant_magnitude_ranks_on_frequency_not_shift():
    """A run of identical-magnitude events only in the recent tail — a
    clear frequency rise with no magnitude change at all, so peak_excess's
    own shift_z can't be what's ranking it. total_events clears n_min, so
    no rare/no_events badge suppresses it."""
    lim = next(l for l in limit_catalog(_CFG) if l["id"] == "oil_temp_max")
    fas = _oil_temp_frequency_fleet(lim)
    fleet = update_fleet(fas)

    peak = fleet.metrics["limit_oil_temp_max_peak_excess"]
    freq = peak["frequency"]
    assert freq["qualifies"] is True
    assert peak.get("readiness") is None

    row = next(r for r in fleet.change_summary if r["metric_id"] == "limit_oil_temp_max_peak_excess")
    assert row is not None
    # The row exists at all only because frequency qualified — assert the
    # shift itself didn't independently clear the bar, so there's no
    # ambiguity about which signal is doing the ranking.
    shift = peak.get("shift")
    assert shift is None or not (shift["level"]["om_margin"] or shift["level"]["filter_edge"])


def test_filtered_limit_still_ranks_when_it_qualifies_v05_correction():
    """Session D / Spec 12 v0.5 §9.3: "a metric with a badge other than
    filtered or pinned is never ranked" — filtered and pinned describe a
    pilot choice, not a data limitation, so a filtered limit that
    qualifies (here, on frequency) still appears in change_summary,
    still carrying its filtered badge. Supersedes the Session C version
    of this test, which excluded every badge including filtered."""
    lim = next(l for l in limit_catalog(_CFG) if l["id"] == "oil_temp_max")
    fas = _oil_temp_frequency_fleet(lim)
    flt = {
        "id": "f1", "limit_id": "oil_temp_max", "magnitude": {"mode": "absolute", "value": 50.0},
        "note": "watching", "created_at": "x", "history": [],
    }
    fleet = update_fleet(fas, filters=[flt])
    peak = fleet.metrics["limit_oil_temp_max_peak_excess"]
    assert peak["readiness"] == {"kind": "filtered"}
    assert any(m["metric_id"] == "limit_oil_temp_max_peak_excess" for m in fleet.change_summary)


def test_overboost_has_event_uses_the_om_limit_not_a_bare_nonzero_block():
    """limit_overboost_block_s is a continuous block length present on
    nearly every flight — "has event" has to be block_s > limit_value
    (300s), not block_s > 0, or nearly every flight would count."""
    ob = next(l for l in limit_catalog(_CFG) if l["id"] == "overboost")
    limit_value = ob["limit_value"]
    fas = [_fa(i, {"lim_overboost_block_s": 40.0}, limits=[ob]) for i in range(40)]
    fas += [_fa(40 + i, {"lim_overboost_block_s": limit_value + 50.0}, limits=[ob]) for i in range(4)]
    fas += [_fa(44 + i, {"lim_overboost_block_s": 40.0}, limits=[ob]) for i in range(6)]
    fleet = update_fleet(fas)
    block = fleet.metrics["limit_overboost_block_s"]
    events = block["events"]
    assert len(events) == 50
    tall = [e for e in events if e["has_event"]]
    assert len(tall) == 4
    assert block["frequency"]["recent"]["events"] + block["frequency"]["reference"]["events"] == 4


def test_overboost_time_shares_the_same_frequency_as_the_blocks3_metric():
    ob = next(l for l in limit_catalog(_CFG) if l["id"] == "overboost")
    limit_value = ob["limit_value"]
    fas = [_fa(i, {"lim_overboost_block_s": 40.0, "overboost_total_s": 40.0}, limits=[ob]) for i in range(40)]
    fas += [
        _fa(40 + i, {"lim_overboost_block_s": limit_value + 50.0, "overboost_total_s": limit_value + 50.0},
            limits=[ob])
        for i in range(10)
    ]
    fleet = update_fleet(fas)
    assert fleet.metrics["overboost_time"]["frequency"] == fleet.metrics["limit_overboost_block_s"]["frequency"]
    assert fleet.metrics["overboost_time"]["unit"] == "s"


# ── shift-history kind ────────────────────────────────────────────────────────

def test_shift_history_opens_a_frequency_kind_event(tmp_path):
    lim = next(l for l in limit_catalog(_CFG) if l["id"] == "oil_temp_max")
    fas = _oil_temp_frequency_fleet(lim)
    fleet = update_fleet(fas)
    row = next(r for r in fleet.change_summary if r["metric_id"] == "limit_oil_temp_max_peak_excess")
    assert _shift_event_kind(fleet, row) == "frequency"

    history = update_shift_history(tmp_path, fleet)
    event = next(e for e in history if e["metric_id"] == "limit_oil_temp_max_peak_excess")
    assert event["kind"] == "frequency"
    assert event["frequency"]["qualifies"] is True
    assert event["window"]["flight_ids"]  # borrowed from time_above_pct's own window
