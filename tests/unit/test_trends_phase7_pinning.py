"""
Spec 12 v0.5, Session D Phase 7 — pinned-reference UX engine support
(§5.7.1 items 4/5, §15 acceptance 16): `cleared_by: "unpin"` and
`preview_clear_reference`, exercised against a real workspace (not just
update_fleet in isolation) so the full set_reference -> rebuild ->
clear_reference path is covered end to end.
"""
from pathlib import Path

from slingology_eis import workspace as ws

from ..contract.test_trends import _fa  # shared synthetic FlightAnalysis builder


def _new_workspace(tmp_path: Path) -> Path:
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "pin-test", "916iS")
    return root / manifest.id


def _seed(ws_dir: Path) -> None:
    """40 quiet flights (egt_spread 50.0) then 10 more quiet flights —
    nothing qualifies under the natural rolling reference."""
    for i in range(50):
        ws.save_flight_analysis(ws_dir, _fa(i, {"egt_spread_mean_f": 50.0}))


def test_pinning_to_a_different_reference_opens_a_shift_event(tmp_path):
    ws_dir = _new_workspace(tmp_path)
    _seed(ws_dir)
    fleet = ws.rebuild_fleet(ws_dir)
    assert fleet.metrics["egt_spread"].get("shift", {}).get("qualifies") is not True

    # Pin to 10 of the early flights, overwritten here to a visibly
    # lower value — a reference the rolling mechanism would never have
    # chosen on its own, so any shift that appears is attributable to
    # the pin (and 10 clears n_min, unlike a too-small pin would).
    pin_ids = [f"f{i:04d}" for i in range(10)]
    for i in range(10):
        fa = ws.load_flight_analysis(ws_dir, f"f{i:04d}")
        fa.metrics["egt_spread_mean_f"]["value"] = 18.0 + i  # 18..27
        ws.save_flight_analysis(ws_dir, fa)
    ws.set_reference(ws_dir, "egt_spread", pin_ids)

    fleet = ws.rebuild_fleet(ws_dir)
    shift = fleet.metrics["egt_spread"]["shift"]
    assert shift["reference"]["kind"] == "pinned"
    assert shift["qualifies"] is True
    open_events = [e for e in fleet.shift_history if e["metric_id"] == "egt_spread" and "cleared_at" not in e]
    assert len(open_events) == 1


def test_unpin_closes_the_event_with_cleared_by_unpin(tmp_path):
    ws_dir = _new_workspace(tmp_path)
    _seed(ws_dir)
    pin_ids = [f"f{i:04d}" for i in range(10)]
    for i in range(10):
        fa = ws.load_flight_analysis(ws_dir, f"f{i:04d}")
        fa.metrics["egt_spread_mean_f"]["value"] = 18.0 + i  # 18..27
        ws.save_flight_analysis(ws_dir, fa)
    ws.set_reference(ws_dir, "egt_spread", pin_ids)
    fleet = ws.rebuild_fleet(ws_dir)
    assert fleet.metrics["egt_spread"]["shift"]["qualifies"] is True

    # Preview, before committing: unpinning reverts to a rolling
    # reference dominated by the 50.0 flights, matching the recent
    # window — the shift should disappear.
    preview = ws.preview_clear_reference(ws_dir, "egt_spread")
    assert preview == {"currently_in_summary": True, "would_be_in_summary": False, "changes": True}

    fleet = ws.clear_reference(ws_dir, "egt_spread")  # FleetSelection, but also rebuilds+saves as a side effect
    rebuilt = ws.load_fleet_analysis(ws_dir)
    assert rebuilt.metrics["egt_spread"]["shift"]["reference"]["kind"] == "rolling"
    assert rebuilt.metrics["egt_spread"]["shift"].get("qualifies") is not True

    event = next(e for e in rebuilt.shift_history if e["metric_id"] == "egt_spread")
    assert event["cleared_by"] == "unpin"
    assert "cleared_at" in event

    # The preview's prediction matches what actually happened.
    assert preview["would_be_in_summary"] == any(
        r["metric_id"] == "egt_spread" for r in rebuilt.change_summary
    )


def test_preview_clear_reference_persists_nothing(tmp_path):
    ws_dir = _new_workspace(tmp_path)
    _seed(ws_dir)
    pin_ids = [f"f{i:04d}" for i in range(10)]
    for i in range(10):
        fa = ws.load_flight_analysis(ws_dir, f"f{i:04d}")
        fa.metrics["egt_spread_mean_f"]["value"] = 18.0 + i  # 18..27
        ws.save_flight_analysis(ws_dir, fa)
    ws.set_reference(ws_dir, "egt_spread", pin_ids)
    ws.rebuild_fleet(ws_dir)

    before = ws.load_selection(ws_dir).baseline_config
    ws.preview_clear_reference(ws_dir, "egt_spread")
    after = ws.load_selection(ws_dir).baseline_config
    assert before == after
    assert "egt_spread" in (after.get("pinned_references") or {})


def test_preview_with_no_pin_reports_no_change():
    """Unpinning a metric that was never pinned (e.g. a stray RPC call)
    is a predictable no-op, not an error — currently/would-be agree."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ws_dir = _new_workspace(Path(tmp))
        _seed(ws_dir)
        ws.rebuild_fleet(ws_dir)
        preview = ws.preview_clear_reference(ws_dir, "egt_spread")
        assert preview["changes"] is False
