"""
Spec 14 v0.13: no Settings changelog; changed settings are Journal
entries (§5, §6.1, §6.3). Acceptance 2 (server side) and 20.
"""
import json

from slingology_eis import workspace as ws

from .test_server import _import_oil_temp_flight, _node_host, isolated_packaged_home, registry_server, rpc  # noqa: F401

SHIPPED = {"membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 2.0,
           "recent_window_hours": 10, "recent_window_min_flights": 5, "recent_window_max_flights": 15,
           "om_margin_fraction": 0.25}


def _journal(url):
    return rpc(url, "get_journal", {})["result"]["entries"]


def _settings(url):
    return [e for e in _journal(url) if e["kind"] == "changed_setting"]


def _save(url, **changes):
    current = rpc(url, "get_fleet", {})["result"]["provenance"]["baseline_config"]
    res = rpc(url, "save_baseline_config", {"baseline_config": {**current, **changes}})
    assert res["ok"], res
    return res["result"]


def _ws_dir():
    reg = ws.load_registry(ws.resolve_registry_path())
    return ws.resolve_workspaces_root() / reg.workspaces[0].id


def _twelve_flights(url):
    rpc(url, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    temps = [180, 182, 178, 181, 179, 183, 177, 180, 182, 178, 181, 179]
    return [_import_oil_temp_flight(url, i + 1, t) for i, t in enumerate(temps)]


def test_acceptance_20_changed_settings_are_journal_entries(registry_server):
    url = registry_server
    _twelve_flights(url)
    before = _journal(url)
    assert _settings(url) == []                      # every setting at shipped: no setting entries

    # Global z: one entry, current and shipped values, a live effect.
    _save(url, outlier_z_threshold=0.5)
    [z] = _settings(url)
    assert z["ref_id"] == "outlier_z_threshold" and z["what"] == "Setting: Outlier z-threshold"
    assert z["current"] == "0.5 (shipped: 2.0)"
    assert z["effect"]["zero"] is False and "compared with shipped" in z["effect"]["text"]
    assert "insight" in z["effect"]["text"]

    # A further change updates it in place.
    _save(url, outlier_z_threshold=0.7)
    [z2] = _settings(url)
    assert z2["id"] == z["id"] and z2["created_at"] == z["created_at"] and z2["updated_at"] > z["updated_at"]
    assert z2["current"] == "0.7 (shipped: 2.0)"

    # A per-metric override and the recent window: one entry each.
    _save(url, outlier_z_threshold_overrides={"oil_temp_peak": 3.0}, recent_window_hours=20)
    by_ref = {e["ref_id"]: e for e in _settings(url)}
    assert set(by_ref) == {"outlier_z_threshold", "outlier_z_threshold_overrides:oil_temp_peak", "recent_window"}
    assert by_ref["outlier_z_threshold_overrides:oil_temp_peak"]["current"] == "3.0 (shipped: follows the global value)"
    assert by_ref["recent_window"]["current"] == "20 h, 5–15 flights (shipped: 10 h, 5–15 flights)"

    # Settings' view: the same settings, each linked to its entry.
    listed = {s["ref_id"]: s for s in rpc(url, "list_changed_settings", {})["result"]["settings"]}
    assert {k: v["entry_id"] for k, v in listed.items()} == {k: v["id"] for k, v in by_ref.items()}
    assert listed["outlier_z_threshold"]["shipped"] == "2.0"

    # Reset to shipped removes the entry and leaves that setting at shipped,
    # the others untouched.
    fleet = rpc(url, "reset_setting", {"ref_id": "outlier_z_threshold"})["result"]
    bc = fleet["provenance"]["baseline_config"]
    assert bc["outlier_z_threshold"] == 2.0 and bc["recent_window_hours"] == 20
    assert bc["outlier_z_threshold_overrides"] == {"oil_temp_peak": 3.0}
    assert {e["ref_id"] for e in _settings(url)} == {"outlier_z_threshold_overrides:oil_temp_peak", "recent_window"}
    rpc(url, "reset_setting", {"ref_id": "outlier_z_threshold_overrides:oil_temp_peak"})
    rpc(url, "reset_setting", {"ref_id": "recent_window"})
    bc = rpc(url, "get_fleet", {})["result"]["provenance"]["baseline_config"]
    assert {k: bc.get(k, SHIPPED.get(k)) for k in SHIPPED} == SHIPPED and not bc.get("outlier_z_threshold_overrides")
    assert _settings(url) == []

    # Back at shipped, the Journal is exactly what it was.
    after = _journal(url)
    assert [(e["kind"], e["ref_id"]) for e in after] == [(e["kind"], e["ref_id"]) for e in before]


def test_a_setting_edited_back_to_shipped_has_no_entry_and_a_save_without_change_keeps_it(registry_server):
    url = registry_server
    rpc(url, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    _save(url, om_margin_fraction=0.4)
    [entry] = _settings(url)
    assert entry["current"] == "0.4 (shipped: 0.25)"
    _save(url, om_margin_fraction=0.4)                 # nothing different: same entry, not touched
    [same] = _settings(url)
    assert same["updated_at"] == entry["updated_at"]
    _save(url, om_margin_fraction=0.25)                # edited back to shipped by hand
    assert _settings(url) == []


def _pins():
    return set((ws.load_selection(_ws_dir()).baseline_config or {}).get("pinned_references") or {})


def test_settings_saves_and_resets_keep_pinned_references(registry_server):
    """Pins are their own decisions: a Settings save (which sends the
    fleet's provenance copy, without pins), a reset of one setting, and a
    whole-panel reset all leave them as stored."""
    url = registry_server
    fid = _twelve_flights(url)[0]
    rpc(url, "set_reference", {"metric_id": "oil_temp_peak", "flight_ids": [fid], "label": "after the overhaul"})
    _save(url, outlier_z_threshold=3.0)
    assert _pins() == {"oil_temp_peak"}
    rpc(url, "reset_setting", {"ref_id": "outlier_z_threshold"})
    assert _pins() == {"oil_temp_peak"}
    rpc(url, "save_baseline_config", {"baseline_config": dict(SHIPPED)})      # "Reset to shipped defaults"
    assert _pins() == {"oil_temp_peak"}
    assert [e["kind"] for e in _journal(url)].count("reference_pin") == 1


def test_display_only_settings_get_no_entry(registry_server):
    url = registry_server
    rpc(url, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    app = rpc(url, "get_app_settings", {})["result"]
    rpc(url, "save_app_settings", {"settings": {**app, "units": "metric"}})
    wss = rpc(url, "get_workspace_settings", {})["result"]
    rpc(url, "save_workspace_settings", {"settings": {**wss, "aircraft_aliases": [["N117ZS", "N117Z"]]}})
    assert _journal(url) == []
    assert rpc(url, "list_changed_settings", {})["result"]["settings"] == []


def test_acceptance_2_no_changelog_is_written_read_or_served(registry_server):
    url = registry_server
    rpc(url, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    ws_dir = _ws_dir()
    old = ws_dir / "settings_changelog.json"
    old.write_text(json.dumps({"version": "1", "entries": [
        {"id": "chg_1", "at": "2026-10-01T00:00:00+00:00", "tab": "reference", "setting": "outlier_z_threshold",
         "before": 2.0, "after": 3.0, "source": "user"}]}))
    content = old.read_bytes()

    gone = rpc(url, "get_settings_changelog", {})
    assert gone["ok"] is False and gone["error"]["code"] == "UNKNOWN_OP"
    _save(url, outlier_z_threshold=3.0)
    app = rpc(url, "get_app_settings", {})["result"]
    rpc(url, "save_app_settings", {"settings": {**app, "units": "metric"}})
    assert old.read_bytes() == content                 # untouched, not deleted
    # Not read either: the old entry says nothing to Journal; only the
    # live setting does.
    assert [e["ref_id"] for e in _settings(url)] == ["outlier_z_threshold"]


def test_engine_tab_shows_the_engine_version(registry_server):
    from slingology_eis import __version__
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    assert rpc(registry_server, "get_engine_limits", {})["result"]["engine_version"] == __version__
