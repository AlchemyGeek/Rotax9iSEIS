"""
Spec 12 v0.9, Session G Phase 10 — zoom-based pin (§5.7, §15 acceptance
19): the web now sends `set_reference` whichever flights were visible
in the strip's zoomed x-range, which can be any contiguous mid-history
span, not just the recent window. `set_reference`/`_compute_shift_for_metric`
already accept an arbitrary flight_ids list (Session A/D never
restricted it) — this is the "minimal, reported" engine check the
task asked for, via the replay harness so the pinned span is
exercised against a real chronological sequence, not a bare list.
"""
from pathlib import Path

from slingology_eis import workspace as ws
from slingology_eis.operations import DEFAULT_BASELINE_CONFIG, update_fleet

from ..contract.test_trends import _fa  # shared synthetic FlightAnalysis builder
from ..replay import chronological


def test_pinning_a_mid_history_span_computes_the_shift_against_exactly_those_flights():
    """50 flights, chronologically replayed; flights 20-29 (mid-history,
    neither the earliest nor the recent window) get a visibly different
    mean. Pinning exactly that span must produce a reference whose mean/n
    come from those 10 flights, not the 20 before or after them."""
    fas = []
    for i in range(50):
        # Jitter within the pinned span (76..85, avg 80.5) — a flat 80.0
        # would give the pinned reference zero variance, which the
        # engine's std floor treats as "unmatched" (Session D hit the
        # same pitfall; see tests/unit/test_trends_phase7_pinning.py).
        value = 76.0 + (i - 20) if 20 <= i < 30 else 50.0
        fas.append(_fa(i, {"egt_spread_mean_f": value}))
    ordered = chronological(fas)
    assert [fa.flight_id for fa in ordered] == [fa.flight_id for fa in fas]  # already chronological by construction

    pin_ids = [fa.flight_id for fa in ordered[20:30]]
    fleet = update_fleet(ordered, baseline_config={
        **DEFAULT_BASELINE_CONFIG,
        "pinned_references": {"egt_spread": {"flight_ids": pin_ids, "set_at": "2026-10-10T00:00:00Z"}},
    })

    shift = fleet.metrics["egt_spread"]["shift"]
    assert shift["reference"]["kind"] == "pinned"
    assert shift["reference"]["n"] == 10
    assert shift["reference"]["mean"] == 80.5
    # Flight 0 and flight 49 (outside the pinned span) must not have
    # leaked into the reference statistics.
    assert set(pin_ids).isdisjoint(set(shift["recent"]["flight_ids"]))


def test_pinning_a_mid_history_span_via_the_workspace_round_trip(tmp_path: Path):
    """Same scenario, through set_reference/rebuild_fleet (what the web
    actually calls) rather than update_fleet's baseline_config directly —
    confirms the workspace layer passes an arbitrary mid-history span
    through unchanged."""
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "zoom-pin-test", "916iS")
    ws_dir = root / manifest.id

    for i in range(50):
        value = 76.0 + (i - 20) if 20 <= i < 30 else 50.0
        ws.save_flight_analysis(ws_dir, _fa(i, {"egt_spread_mean_f": value}))

    pin_ids = [f"f{i:04d}" for i in range(20, 30)]
    ws.set_reference(ws_dir, "egt_spread", pin_ids, label="zoomed to 20-29")
    fleet = ws.rebuild_fleet(ws_dir)

    shift = fleet.metrics["egt_spread"]["shift"]
    assert shift["reference"]["kind"] == "pinned"
    assert shift["reference"]["n"] == 10
    assert shift["reference"]["mean"] == 80.5
    assert shift["reference"]["label"] == "zoomed to 20-29"
    assert shift["qualifies"] is True  # ~80.5 vs the surrounding 50s is a large, unmissable shift
