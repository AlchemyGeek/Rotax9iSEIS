"""
Spec 12 Phase 2 — pinned references and shift history (§15 acceptance
5, 6, plus the workspace persistence round-trip for both).
"""
import random

from slingology_eis import workspace as ws
from slingology_eis.operations import FlightAnalysis, update_fleet
from slingology_eis.registry import METRIC_REGISTRY

from ..contract.test_trends import _fa  # shared synthetic FlightAnalysis builder


# ── set_reference / clear_reference persistence ─────────────────────────────

def test_set_reference_persists_and_clear_reference_reverts(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "pins", "916iS")
    ws_dir = root / manifest.id

    selection = ws.set_reference(ws_dir, "egt_spread", ["f1", "f2", "f3"], label="pre-overhaul")
    assert selection.baseline_config["pinned_references"]["egt_spread"]["flight_ids"] == ["f1", "f2", "f3"]
    assert selection.baseline_config["pinned_references"]["egt_spread"]["label"] == "pre-overhaul"
    assert "set_at" in selection.baseline_config["pinned_references"]["egt_spread"]

    # Round-trips through disk, not just the in-memory object.
    reloaded = ws.load_selection(ws_dir)
    assert reloaded.baseline_config["pinned_references"]["egt_spread"]["flight_ids"] == ["f1", "f2", "f3"]

    selection = ws.clear_reference(ws_dir, "egt_spread")
    assert "egt_spread" not in selection.baseline_config["pinned_references"]
    assert "egt_spread" not in ws.load_selection(ws_dir).baseline_config["pinned_references"]


def test_clear_reference_on_an_unpinned_metric_is_a_no_op(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "noop", "916iS")
    ws_dir = root / manifest.id
    selection = ws.clear_reference(ws_dir, "egt_spread")
    assert selection.baseline_config.get("pinned_references", {}) == {}


# ── Acceptance 5: rolling vs. pinned ─────────────────────────────────────────

def test_pinned_reference_catches_a_drift_rolling_reference_absorbs():
    """A slow synthetic drift (0.01 units/flight against noise std 1.0,
    seeded): the rolling reference is "every flight older than the
    window" — over 100 flights it already contains most of the drift,
    so it reads as normal variation. Pinned to the first 20 (drift-free)
    flights, the same recent window reads as a real shift."""
    n = 100
    rng = random.Random(1)
    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + 0.01 * i + rng.gauss(0, 1.0)}) for i in range(n)]

    rolling_fleet = update_fleet(fas)
    rolling_shift = rolling_fleet.metrics["egt_spread"]["shift"]
    assert rolling_shift["qualifies"] is False

    pinned_cfg = {"pinned_references": {"egt_spread": {"flight_ids": [fa.flight_id for fa in fas[:20]]}}}
    pinned_fleet = update_fleet(fas, baseline_config=pinned_cfg)
    pinned_shift = pinned_fleet.metrics["egt_spread"]["shift"]
    assert pinned_shift["reference"]["kind"] == "pinned"
    assert pinned_shift["qualifies"] is True

    # Unpinning (empty pinned_references) restores the rolling result.
    unpinned_fleet = update_fleet(fas, baseline_config={"pinned_references": {}})
    unpinned_shift = unpinned_fleet.metrics["egt_spread"]["shift"]
    assert unpinned_shift["reference"]["kind"] == "rolling"
    assert unpinned_shift["qualifies"] is False


def test_pinned_reference_below_n_min_reverts_to_rolling_with_warning():
    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + 0.5 * i}) for i in range(50)]
    pinned_cfg = {"pinned_references": {"egt_spread": {"flight_ids": [fas[0].flight_id, fas[1].flight_id]}}}
    fleet = update_fleet(fas, baseline_config=pinned_cfg)
    shift = fleet.metrics["egt_spread"]["shift"]
    assert shift["reference"]["kind"] == "rolling"
    codes = {d["code"] for d in fleet.quality}
    assert "REFERENCE_LOW_N" in codes


# ── Acceptance 6: shift history ──────────────────────────────────────────────

def test_shift_history_opens_and_closes_one_event_and_is_idempotent(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "hist", "916iS")
    ws_dir = root / manifest.id

    qualifying_fas = [_fa(i, {"egt_spread_mean_f": 50.0 + (i % 3) * 0.1}) for i in range(30)]
    qualifying_fas += [_fa(30 + i, {"egt_spread_mean_f": 80.0 + (i % 3) * 0.1}) for i in range(10)]
    fleet_on = update_fleet(qualifying_fas)
    assert fleet_on.metrics["egt_spread"]["shift"]["qualifies"] is True

    history = ws.update_shift_history(ws_dir, fleet_on)
    assert len(history) == 1
    assert history[0]["metric_id"] == "egt_spread"
    assert "cleared_at" not in history[0]
    assert history[0]["detected_at"]

    # Re-running update_fleet with the SAME flights and re-merging history
    # must not duplicate the open event — still appends nothing.
    fleet_on_again = update_fleet(qualifying_fas)
    history_again = ws.update_shift_history(ws_dir, fleet_on_again)
    assert len(history_again) == 1
    assert history_again[0]["id"] == history[0]["id"]

    # Metric returns to normal: a steady run of flights at the old level.
    clearing_fas = qualifying_fas + [_fa(40 + i, {"egt_spread_mean_f": 50.0 + (i % 3) * 0.1}) for i in range(15)]
    fleet_cleared = update_fleet(clearing_fas)
    assert fleet_cleared.metrics["egt_spread"]["shift"]["qualifies"] is False

    history_cleared = ws.update_shift_history(ws_dir, fleet_cleared)
    assert len(history_cleared) == 1  # still one event — closed, not duplicated
    assert history_cleared[0]["cleared_at"]
    assert history_cleared[0]["id"] == history[0]["id"]

    # Persisted to disk, not just returned in memory.
    assert ws.load_shift_history(ws_dir) == history_cleared


def test_delete_shift_event_removes_it(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "del", "916iS")
    ws_dir = root / manifest.id

    fas = [_fa(i, {"egt_spread_mean_f": 50.0 + (i % 3) * 0.1}) for i in range(30)]
    fas += [_fa(30 + i, {"egt_spread_mean_f": 80.0 + (i % 3) * 0.1}) for i in range(10)]
    fleet = update_fleet(fas)
    history = ws.update_shift_history(ws_dir, fleet)
    event_id = history[0]["id"]

    remaining = ws.delete_shift_event(ws_dir, event_id)
    assert remaining == []
    assert ws.load_shift_history(ws_dir) == []
