"""
tests/unit/test_workspace.py — Spec 02 v0.5 workspace model.

Split into two groups: synthetic-data tests for the document shapes and
selection/settings logic (no real logs needed), and real-log tests
(`requires_flight_logs`) that exercise `scan_workspace` end to end —
fingerprint rematching, missing-vs-unreachable, and duplicate-export
handling all need actual parseable CSVs to mean anything.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from slingology_eis import workspace as ws
from ..conftest import LOGS_DIR, requires_flight_logs

# Two small real logs, same aircraft (KTOA tail), used across the
# real-log tests below.
_LOG_A = LOGS_DIR / "log_20260408_101333_KTOA.csv"
_LOG_B = LOGS_DIR / "log_20260408_103004_KTOA.csv"


# ── Registry ──────────────────────────────────────────────────────────────

def test_create_workspace_appends_to_registry(tmp_path):
    registry_path = tmp_path / "registry.json"
    workspaces_root = tmp_path / "workspaces"

    manifest = ws.create_workspace(registry_path, workspaces_root, "N117ZS — all", "916iS")

    registry = ws.load_registry(registry_path)
    assert [w.name for w in registry.workspaces] == ["N117ZS — all"]
    entry = registry.workspaces[0]
    assert entry.id == manifest.id
    assert entry.engine_model == "916iS"
    assert entry.flight_count == 0

    # per-workspace layout exists
    ws_dir = workspaces_root / manifest.id
    assert (ws_dir / "manifest.json").exists()
    assert (ws_dir / "flights").is_dir()
    assert (ws_dir / "fleet" / "selection.json").exists()
    assert (ws_dir / "settings.json").exists()


def test_create_workspace_rejects_unknown_engine_model(tmp_path):
    with pytest.raises(ValueError):
        ws.create_workspace(tmp_path / "registry.json", tmp_path / "workspaces", "test", "917iS")


def test_create_workspace_rejects_duplicate_name(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    ws.create_workspace(registry_path, root, "dupe", "916iS")
    with pytest.raises(ValueError):
        ws.create_workspace(registry_path, root, "dupe", "916iS")


def test_resolve_workspace_ref_by_name_and_id(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "N117ZS", "916iS")

    assert ws.resolve_workspace_ref("N117ZS", registry_path, root) == root / manifest.id
    assert ws.resolve_workspace_ref(manifest.id, registry_path, root) == root / manifest.id


def test_resolve_workspace_ref_falls_back_to_literal_path(tmp_path):
    """A path that isn't a registered name/id — the pre-registry CLI
    behavior (Spec 01 v0.6 §7.1, Q10) must keep working exactly as-is."""
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    some_dir = tmp_path / "my-checkout" / "data"
    result = ws.resolve_workspace_ref(str(some_dir), registry_path, root)
    assert result == some_dir


# ── FleetSelection: no included list ─────────────────────────────────────

def test_fleet_selection_round_trip_has_no_included_field(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "sel", "916iS")
    ws_dir = root / manifest.id

    selection = ws.load_selection(ws_dir)
    assert selection.excluded == []
    assert "included" not in selection.to_dict()

    ws.exclude_flight(ws_dir, "abc123", "known-bad log")
    selection = ws.load_selection(ws_dir)
    assert selection.excluded == [{"flight_id": "abc123", "reason": "known-bad log"}]
    assert "included" not in selection.to_dict()

    ws.include_flight(ws_dir, "abc123")
    assert ws.load_selection(ws_dir).excluded == []


def test_exclude_flight_is_idempotent(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "idem", "916iS")
    ws_dir = root / manifest.id
    ws.exclude_flight(ws_dir, "abc", "x")
    ws.exclude_flight(ws_dir, "abc", "x")
    assert len(ws.load_selection(ws_dir).excluded) == 1


# ── Settings split ────────────────────────────────────────────────────────

def test_app_and_workspace_settings_are_separate_documents(tmp_path):
    registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
    manifest = ws.create_workspace(registry_path, root, "settings-test", "916iS")
    ws_dir = root / manifest.id

    app = ws.AppSettings(units="metric", last_active_workspace_id=manifest.id)
    ws.save_app_settings(registry_path, app)
    loaded_app = ws.load_app_settings(registry_path)
    assert loaded_app.units == "metric"
    assert loaded_app.last_active_workspace_id == manifest.id

    wss = ws.load_workspace_settings(ws_dir)
    assert wss.active_engine_profile == "916iS"  # set at creation
    assert "units" not in wss.to_dict()
    assert "last_active_workspace_id" not in wss.to_dict()

    # the two documents live in different files
    assert (registry_path.parent / "settings.json").exists()
    assert (ws_dir / "settings.json").exists()
    assert (registry_path.parent / "settings.json") != (ws_dir / "settings.json")


# ── engine_model: locked, never per-log ──────────────────────────────────

def test_engine_model_is_not_a_creatable_field_on_manifest_after_the_fact(tmp_path):
    """There is deliberately no `set_engine_model` — engine_model is
    locked at creation (§5.6). This test documents that by asserting the
    module exposes no such function, so a future edit reintroducing one
    fails loudly here instead of silently."""
    assert not hasattr(ws, "set_engine_model")
    assert not hasattr(ws, "update_engine_model")


# ── Missing vs unreachable folder — real logs required ───────────────────

@requires_flight_logs
class TestScanWithRealLogs:
    def _new_workspace(self, tmp_path):
        registry_path, root = tmp_path / "registry.json", tmp_path / "workspaces"
        manifest = ws.create_workspace(registry_path, root, "scan-test", "916iS")
        return registry_path, root, root / manifest.id

    def test_scan_finds_new_flights(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)

        ws.add_log_folder(ws_dir, str(folder), registry_path)
        result = ws.scan_workspace(ws_dir, registry_path)

        assert len(result.new_flight_ids) == 1
        assert ws.list_flight_ids(ws_dir) == result.new_flight_ids
        manifest = ws.load_manifest(ws_dir)
        assert manifest.flight_count == 1
        assert manifest.log_folders[0].reachable is True

        registry_entry = ws.load_registry(registry_path).workspaces[0]
        assert registry_entry.flight_count == 1

    def test_rescan_is_idempotent(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        ws.scan_workspace(ws_dir, registry_path)

        result2 = ws.scan_workspace(ws_dir, registry_path)
        assert result2.new_flight_ids == []
        assert result2.now_missing_flight_ids == []
        assert len(ws.list_flight_ids(ws_dir)) == 1

    def test_rescan_reanalyzes_flights_stale_relative_to_running_engine(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        [fid] = ws.scan_workspace(ws_dir, registry_path).new_flight_ids

        # Simulate a flight analyzed by an older engine — same content on
        # disk, unchanged path, but the stored analysis predates now.
        fa = ws.load_flight_analysis(ws_dir, fid)
        fa.provenance["engine_version"] = "0.0.1"
        fa.metrics = {}  # a real behavior change an older engine wouldn't have produced
        ws.save_flight_analysis(ws_dir, fa)

        result = ws.scan_workspace(ws_dir, registry_path)
        assert result.reanalyzed_flight_ids == [fid]
        assert result.new_flight_ids == []

        refreshed = ws.load_flight_analysis(ws_dir, fid)
        assert refreshed.provenance["engine_version"] == ws.__version__
        assert refreshed.metrics != {}  # actually re-ran analyze_flight, not just touched provenance

        # Idempotent — a flight already current isn't reanalyzed again.
        again = ws.scan_workspace(ws_dir, registry_path)
        assert again.reanalyzed_flight_ids == []

    def test_rename_moved_file_rematches_by_fingerprint(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        dest = folder / _LOG_A.name
        shutil.copy(_LOG_A, dest)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        first = ws.scan_workspace(ws_dir, registry_path)
        [fid] = first.new_flight_ids

        # rename in place — same folder, same fingerprint, different filename
        renamed = folder / "renamed_flight.csv"
        dest.rename(renamed)
        second = ws.scan_workspace(ws_dir, registry_path)

        assert second.new_flight_ids == []
        assert fid in second.rematched_flight_ids
        sources = ws.load_sources(ws_dir, fid)
        assert sources.imports[0].filename == "renamed_flight.csv"
        assert not sources.missing
        # still exactly one flight — not a duplicate
        assert len(ws.list_flight_ids(ws_dir)) == 1

    def test_moved_to_different_known_folder_rematches(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder_a = tmp_path / "folder_a"
        folder_b = tmp_path / "folder_b"
        folder_a.mkdir()
        folder_b.mkdir()
        dest = folder_a / _LOG_A.name
        shutil.copy(_LOG_A, dest)
        ws.add_log_folder(ws_dir, str(folder_a), registry_path)
        ws.add_log_folder(ws_dir, str(folder_b), registry_path)
        first = ws.scan_workspace(ws_dir, registry_path)
        [fid] = first.new_flight_ids

        shutil.move(str(dest), str(folder_b / _LOG_A.name))
        second = ws.scan_workspace(ws_dir, registry_path)

        assert fid in second.rematched_flight_ids
        sources = ws.load_sources(ws_dir, fid)
        assert sources.imports[0].log_folder_path == str(folder_b)

    def test_missing_log_persists_and_keeps_baseline_contribution(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        dest = folder / _LOG_A.name
        shutil.copy(_LOG_A, dest)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        first = ws.scan_workspace(ws_dir, registry_path)
        [fid] = first.new_flight_ids

        dest.unlink()  # genuinely deleted, folder itself still reachable
        second = ws.scan_workspace(ws_dir, registry_path)

        assert fid in second.now_missing_flight_ids
        sources = ws.load_sources(ws_dir, fid)
        assert sources.missing is True
        # the flight is NOT dropped from the workspace
        assert fid in ws.list_flight_ids(ws_dir)

        # and NOT excluded from the fleet — baseline contribution unchanged (§5.5)
        fleet = ws.rebuild_fleet(ws_dir)
        assert fid in fleet.flight_ids

        # a third scan with the file still gone must not re-flag it (already missing)
        third = ws.scan_workspace(ws_dir, registry_path)
        assert third.now_missing_flight_ids == []

    def test_missing_log_recovers_if_refound(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        dest = folder / _LOG_A.name
        shutil.copy(_LOG_A, dest)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        [fid] = ws.scan_workspace(ws_dir, registry_path).new_flight_ids

        dest.unlink()
        ws.scan_workspace(ws_dir, registry_path)
        assert ws.load_sources(ws_dir, fid).missing is True

        shutil.copy(_LOG_A, dest)  # "reconnected the drive"
        result = ws.scan_workspace(ws_dir, registry_path)
        assert fid in result.recovered_flight_ids
        assert ws.load_sources(ws_dir, fid).missing is False

    def test_unreachable_folder_is_one_event_not_per_flight(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)
        shutil.copy(_LOG_B, folder / _LOG_B.name)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        first = ws.scan_workspace(ws_dir, registry_path)
        assert len(first.new_flight_ids) == 2

        shutil.rmtree(folder)  # the whole folder disappears (unplugged drive)
        second = ws.scan_workspace(ws_dir, registry_path)

        assert second.unreachable_folders == [str(folder)]
        # neither flight gets individually flagged missing — we never got
        # to check the one place they might still be
        assert second.now_missing_flight_ids == []
        for fid in ws.list_flight_ids(ws_dir):
            assert ws.load_sources(ws_dir, fid).missing is False

        manifest = ws.load_manifest(ws_dir)
        assert manifest.log_folders[0].reachable is False

    def test_remove_missing_flight_requires_missing_flag(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        dest = folder / _LOG_A.name
        shutil.copy(_LOG_A, dest)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        [fid] = ws.scan_workspace(ws_dir, registry_path).new_flight_ids

        # present flight — refuses to remove
        assert ws.remove_missing_flight(ws_dir, fid) is False
        assert fid in ws.list_flight_ids(ws_dir)

        dest.unlink()
        ws.scan_workspace(ws_dir, registry_path)
        assert ws.remove_missing_flight(ws_dir, fid) is True
        assert fid not in ws.list_flight_ids(ws_dir)

    def test_remove_flight_works_regardless_of_status_and_drops_exclusion(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        [fid] = ws.scan_workspace(ws_dir, registry_path).new_flight_ids

        # present, non-missing flight — remove_missing_flight refuses, remove_flight doesn't
        assert ws.remove_missing_flight(ws_dir, fid) is False
        ws.exclude_flight(ws_dir, fid, "test exclusion")
        assert any(e["flight_id"] == fid for e in ws.load_selection(ws_dir).excluded)

        assert ws.remove_flight(ws_dir, fid) is True
        assert fid not in ws.list_flight_ids(ws_dir)
        assert all(e["flight_id"] != fid for e in ws.load_selection(ws_dir).excluded)

        # removing again (already gone) reports False, doesn't raise
        assert ws.remove_flight(ws_dir, fid) is False

    def test_remove_flights_bulk_removes_and_drops_exclusions(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)
        shutil.copy(_LOG_B, folder / _LOG_B.name)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        scanned = ws.scan_workspace(ws_dir, registry_path)
        fid_a, fid_b = scanned.new_flight_ids
        ws.exclude_flight(ws_dir, fid_a, "test exclusion")

        removed = ws.remove_flights(ws_dir, [fid_a, fid_b, "not_a_real_id"])
        assert set(removed) == {fid_a, fid_b}
        assert fid_a not in ws.list_flight_ids(ws_dir)
        assert fid_b not in ws.list_flight_ids(ws_dir)
        assert ws.load_selection(ws_dir).excluded == []

    def test_load_workspace_rules_falls_back_to_shipped(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        shipped = {"version": "1.1", "rules": {"overboost_time": {"triggers": [{"type": "threshold", "limit": 300}]}}}

        # no active.json yet — resolves to the shipped copy passed in
        assert ws.load_workspace_rules(ws_dir, shipped) == shipped

        edited = {"version": "1.1", "rules": {"overboost_time": {"triggers": [{"type": "threshold", "limit": 200}]}}}
        ws.save_workspace_rules(ws_dir, edited)
        assert ws.load_workspace_rules(ws_dir, shipped) == edited

        ws.reset_workspace_rules(ws_dir)
        assert ws.load_workspace_rules(ws_dir, shipped) == shipped
        # idempotent — resetting an already-shipped state doesn't raise
        ws.reset_workspace_rules(ws_dir)

    def test_update_baseline_config_persists_through_selection(self, tmp_path):
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        default_config = ws.load_selection(ws_dir).baseline_config
        assert default_config["outlier_z_threshold"] == 2.0

        new_config = {"membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 1.5,
                      "outlier_z_threshold_overrides": {"overboost_time": 3.0}}
        ws.update_baseline_config(ws_dir, new_config)
        assert ws.load_selection(ws_dir).baseline_config == new_config

    def test_different_tail_number_is_informational_never_excludes(self, tmp_path):
        """Both fixture logs happen to share the same aircraft_ident, so
        this test forges the manifest's primary_tail_number to force a
        mismatch and confirms it's flagged but changes nothing else."""
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        manifest = ws.load_manifest(ws_dir)
        manifest.primary_tail_number = "N999ZZ"  # deliberately not this log's ident
        ws.save_manifest(ws_dir, manifest)

        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)
        ws.add_log_folder(ws_dir, str(folder), registry_path)
        result = ws.scan_workspace(ws_dir, registry_path)
        [fid] = result.new_flight_ids

        sources = ws.load_sources(ws_dir, fid)
        assert sources.different_tail_number is not None
        assert sources.different_tail_number != "N999ZZ"

        # never excluded, never blocks — it's a normal member of the fleet
        selection = ws.load_selection(ws_dir)
        assert selection.excluded == []
        fleet = ws.rebuild_fleet(ws_dir)
        assert fid in fleet.flight_ids

    def test_same_file_in_two_folders_is_one_flight_not_two(self, tmp_path):
        """The same bytes reachable via two different log folder
        references (§5.7's 'same log in two folders... de-duplicated by
        fingerprint, one flight either way') — the second folder's copy
        is the same fingerprint, so it never becomes a second import
        entry; it's invisible to the scan, not merged after the fact."""
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder_a = tmp_path / "a"
        folder_b = tmp_path / "b"
        folder_a.mkdir()
        folder_b.mkdir()
        shutil.copy(_LOG_A, folder_a / _LOG_A.name)
        shutil.copy(_LOG_A, folder_b / "same_flight_copy.csv")
        ws.add_log_folder(ws_dir, str(folder_a), registry_path)
        ws.add_log_folder(ws_dir, str(folder_b), registry_path)

        result = ws.scan_workspace(ws_dir, registry_path)
        assert len(result.new_flight_ids) == 1
        assert len(ws.list_flight_ids(ws_dir)) == 1
        [fid] = result.new_flight_ids
        assert len(ws.load_sources(ws_dir, fid).imports) == 1

    def test_two_export_formats_of_same_flight_both_recorded(self, tmp_path):
        """The real §6.2 case: two *different* files (different bytes —
        an SD-card export and a Garmin Pilot export) that parse to the
        same flight_id (same fingerprint) get two import entries under
        one flight, not two flights. Simulated here by editing one byte
        of a copy so its source_key genuinely differs while its parsed
        fingerprint (aircraft/system/start-minute) stays the same."""
        registry_path, root, ws_dir = self._new_workspace(tmp_path)
        folder = tmp_path / "logs"
        folder.mkdir()
        shutil.copy(_LOG_A, folder / _LOG_A.name)

        content = _LOG_A.read_bytes()
        # Append an irrelevant trailing blank line — changes the byte
        # hash (source_key) without touching any parsed field.
        variant = folder / "variant_export.csv"
        variant.write_bytes(content + b"\n")

        ws.add_log_folder(ws_dir, str(folder), registry_path)
        result = ws.scan_workspace(ws_dir, registry_path)

        assert len(result.new_flight_ids) == 1
        [fid] = result.new_flight_ids
        sources = ws.load_sources(ws_dir, fid)
        assert len(sources.imports) == 2
        assert {i.filename for i in sources.imports} == {_LOG_A.name, "variant_export.csv"}
