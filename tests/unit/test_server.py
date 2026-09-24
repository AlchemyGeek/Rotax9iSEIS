"""
Tests for server.py (Spec 04 §9.2, the local-server adapter).

Starts the real ThreadingHTTPServer on an OS-assigned ephemeral port
(port=0) in a background thread per test, and shuts it down cleanly via
.shutdown() — never calls run_server()/serve_forever() in-process, which
would block the test suite forever (this broke `slingology-eis serve`'s
old CLI stub test when `cmd_serve` was wired to the real server).
"""
import base64
import json
import threading
import urllib.request

import pytest

from slingology_eis import workspace as ws
from slingology_eis.server import build_server


@pytest.fixture
def server(tmp_path):
    httpd = build_server(logs_dir=None, workspace_dir=str(tmp_path), port=0, quiet=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.fixture
def isolated_packaged_home(tmp_path, monkeypatch):
    """
    Spec 02 v0.5 registry tests need resolve_registry_path()/
    resolve_workspaces_root() pointed at an isolated tmp dir — otherwise
    server startup touches this machine's real ~/SlingologyEIS or
    <repo>/data/registry.json, same isolation used in tests/cli/test_cli.py.
    """
    home = tmp_path / "SlingologyEIS"
    home.mkdir()
    monkeypatch.setattr(ws, "_PACKAGED_HOME", home)
    return home


@pytest.fixture
def registry_server(isolated_packaged_home):
    """A server started with no --workspace and no workspaces ever
    created — the registry-aware startup path, not the legacy one the
    plain `server` fixture above exercises."""
    httpd = build_server(logs_dir=None, workspace_dir=None, port=0, quiet=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def rpc(base_url, op, params, request_id="r-1"):
    body = json.dumps({"op": op, "request_id": request_id, "params": params}).encode()
    req = urllib.request.Request(f"{base_url}/rpc", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


_META = (
    'aircraft_ident="N999XX", product="GDU 460", system_id="123456789", '
    'unit="1", airframe_hours="10.5", engine_hours="20.1", log_version="7"\n'
)
_HEADER = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Oil Temp (deg F)\n"
_ROWS = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{2000+i},180\n" for i in range(120))
_SYNTHETIC_LOG = (_META + _HEADER + _ROWS).encode("utf-8")


def test_list_engines(server):
    d = rpc(server, "list_engines", {})
    assert d["ok"]
    assert any(e["id"] == "916iS" for e in d["result"])


def test_get_default_rules(server):
    d = rpc(server, "get_default_rules", {})
    assert d["ok"]
    assert d["result"]["rules"]["overboost_time"]["triggers"][0]["limit"] == 300


def test_unknown_op_returns_envelope_error(server):
    d = rpc(server, "not_a_real_op", {})
    assert d["ok"] is False
    assert d["error"]["code"] == "UNKNOWN_OP"
    assert d["request_id"] == "r-1"


def test_analyze_flight_synthetic_log(server):
    b64 = base64.b64encode(_SYNTHETIC_LOG).decode()
    d = rpc(server, "analyze_flight", {"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"})
    assert d["ok"]
    assert d["result"]["flight_id"]
    assert "metrics" in d["result"]


def test_ingest_ground_session_detection(server):
    # RPM never exceeds 3000 and there's no ias_kt column -> ground session
    b64 = base64.b64encode(_SYNTHETIC_LOG).decode()
    d = rpc(server, "ingest_log", {"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"})
    assert d["ok"]
    assert d["result"]["classification"] == "ground_session"


def test_import_files_then_list_and_get_flight(server):
    # Force it to be classified "new": rpm > 3000 and ias_kt > 30 for the
    # whole file, to clear the ground-session airborne-minutes gate.
    flight_header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Temp (deg F)\n"
    high_rpm_rows = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{4000+i},95,180\n" for i in range(240))
    flight_log = (_META + flight_header + high_rpm_rows).encode("utf-8")
    b64 = base64.b64encode(flight_log).decode()

    imp = rpc(server, "import_files", {"files": [{"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"}]})
    assert imp["ok"], imp
    assert imp["result"]["flight_count"] == 1
    flight_id = imp["result"]["results"][0]["flight_id"]

    flights = rpc(server, "list_flights", {})
    assert flights["ok"]
    assert any(f["flight_id"] == flight_id for f in flights["result"])

    got = rpc(server, "get_flight", {"flight_id": flight_id})
    assert got["ok"], got
    assert got["result"]["flight_analysis"]["flight_id"] == flight_id
    assert "topics" in got["result"]["insight_set"]

    # re-importing the same bytes should now classify as duplicate
    dup = rpc(server, "import_files", {"files": [{"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"}]})
    assert dup["result"]["results"][0]["classification"] == "duplicate"


def test_get_fleet_empty_workspace(server):
    d = rpc(server, "get_fleet", {})
    assert d["ok"]
    assert d["result"]["flight_ids"] == []


def test_legacy_server_reports_no_active_workspace(server):
    d = rpc(server, "get_active_workspace", {})
    assert d["ok"]
    assert d["result"]["active"] is False


def test_legacy_server_workspace_management_ops_require_active_workspace(server):
    d = rpc(server, "add_log_folder", {"path": "/tmp/whatever"})
    assert d["ok"] is False
    assert d["error"]["code"] == "NO_ACTIVE_WORKSPACE"

    d = rpc(server, "scan_workspace", {})
    assert d["ok"] is False
    assert d["error"]["code"] == "NO_ACTIVE_WORKSPACE"


# ── Spec 02 v0.5 workspace management (registry-aware startup) ──────────────

def test_registry_server_starts_with_no_active_workspace(registry_server):
    d = rpc(registry_server, "list_workspaces", {})
    assert d["ok"]
    assert d["result"] == []

    d = rpc(registry_server, "get_active_workspace", {})
    assert d["ok"]
    assert d["result"]["active"] is False


def test_create_workspace_becomes_active(registry_server):
    created = rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    assert created["ok"], created
    assert created["result"]["engine_model"] == "916iS"

    active = rpc(registry_server, "get_active_workspace", {})
    assert active["ok"]
    assert active["result"]["active"] is True
    assert active["result"]["manifest"]["id"] == created["result"]["id"]
    assert active["result"]["registry_entry"]["name"] == "N117ZS"

    listed = rpc(registry_server, "list_workspaces", {})
    assert len(listed["result"]) == 1


def test_create_workspace_rejects_unknown_engine(registry_server):
    d = rpc(registry_server, "create_workspace", {"name": "bad", "engine_model": "917iS"})
    assert d["ok"] is False
    assert d["error"]["code"] == "BAD_PARAMS"


def test_switch_workspace(registry_server):
    a = rpc(registry_server, "create_workspace", {"name": "A", "engine_model": "916iS"})["result"]
    b = rpc(registry_server, "create_workspace", {"name": "B", "engine_model": "912iS"})["result"]

    active = rpc(registry_server, "get_active_workspace", {})["result"]
    assert active["manifest"]["id"] == b["id"]  # most recently created is active

    switched = rpc(registry_server, "switch_workspace", {"workspace_id": a["id"]})
    assert switched["ok"], switched
    assert switched["result"]["manifest"]["id"] == a["id"]

    d = rpc(registry_server, "switch_workspace", {"workspace_id": "nonexistent"})
    assert d["ok"] is False
    assert d["error"]["code"] == "NOT_FOUND"


def test_app_and_workspace_settings_round_trip(registry_server):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    saved = rpc(registry_server, "save_app_settings", {"settings": {"units": "metric", "last_active_workspace_id": None}})
    assert saved["ok"], saved
    got = rpc(registry_server, "get_app_settings", {})
    assert got["result"]["units"] == "metric"

    saved = rpc(registry_server, "save_workspace_settings", {"settings": {
        "anonymize_by_default": True, "active_engine_profile": "916iS",
    }})
    assert saved["ok"], saved
    got = rpc(registry_server, "get_workspace_settings", {})
    assert got["result"]["anonymize_by_default"] is True


def test_add_log_folder_and_scan_finds_real_flight(registry_server, tmp_path):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    folder = tmp_path / "logs"
    folder.mkdir()
    import shutil
    from ..conftest import LOGS_DIR
    src = LOGS_DIR / "log_20260408_101333_KTOA.csv"
    if not src.exists():
        pytest.skip("real flight logs not available in this environment")
    shutil.copy(src, folder / src.name)

    added = rpc(registry_server, "add_log_folder", {"path": str(folder)})
    assert added["ok"], added
    assert added["result"]["log_folders"][0]["path"] == str(folder)

    scanned = rpc(registry_server, "scan_workspace", {})
    assert scanned["ok"], scanned
    assert len(scanned["result"]["new_flight_ids"]) == 1
    flight_id = scanned["result"]["new_flight_ids"][0]

    status_list = rpc(registry_server, "list_flights_with_status", {})
    assert status_list["ok"], status_list
    row = next(r for r in status_list["result"]["rows"] if r["flight_id"] == flight_id)
    assert row["status"] == "analyzed"
    assert row["in_baselines"] is True

    excluded = rpc(registry_server, "exclude_flight", {"flight_id": flight_id, "reason": "test"})
    assert excluded["ok"]
    status_list = rpc(registry_server, "list_flights_with_status", {})
    row = next(r for r in status_list["result"]["rows"] if r["flight_id"] == flight_id)
    assert row["in_baselines"] is False
    assert row["excluded_reason"] == "test"

    included = rpc(registry_server, "include_flight", {"flight_id": flight_id})
    assert included["ok"]
    assert included["result"]["excluded"] == []

    # file goes missing on a rescan — status flips, flight is NOT dropped
    (folder / src.name).unlink()
    rescan = rpc(registry_server, "scan_workspace", {})
    assert flight_id in rescan["result"]["now_missing_flight_ids"]
    status_list = rpc(registry_server, "list_flights_with_status", {})
    row = next(r for r in status_list["result"]["rows"] if r["flight_id"] == flight_id)
    assert row["status"] == "missing"

    removed = rpc(registry_server, "remove_missing_flight", {"flight_id": flight_id})
    assert removed["result"]["removed"] is True
    status_list = rpc(registry_server, "list_flights_with_status", {})
    assert all(r["flight_id"] != flight_id for r in status_list["result"]["rows"])


def test_scan_workspace_reanalyzes_stale_flights_and_rebuilds_fleet(registry_server, tmp_path):
    created = rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    workspace_id = created["result"]["id"]

    import shutil
    from ..conftest import LOGS_DIR
    src = LOGS_DIR / "log_20260408_101333_KTOA.csv"
    if not src.exists():
        pytest.skip("real flight logs not available in this environment")
    folder = tmp_path / "logs"
    folder.mkdir()
    shutil.copy(src, folder / src.name)
    rpc(registry_server, "add_log_folder", {"path": str(folder)})
    scanned = rpc(registry_server, "scan_workspace", {})
    [flight_id] = scanned["result"]["new_flight_ids"]
    assert scanned["result"]["reanalyzed_flight_ids"] == []

    # Simulate staleness directly on disk — not something a pilot does
    # via RPC, this is standing in for "an older engine analyzed this".
    ws_dir = ws.resolve_workspaces_root() / workspace_id
    fa = ws.load_flight_analysis(ws_dir, flight_id)
    fa.provenance["engine_version"] = "0.0.1"
    ws.save_flight_analysis(ws_dir, fa)

    rescanned = rpc(registry_server, "scan_workspace", {})
    assert rescanned["ok"], rescanned
    assert rescanned["result"]["reanalyzed_flight_ids"] == [flight_id]

    refetched = rpc(registry_server, "get_flight", {"flight_id": flight_id})
    assert refetched["result"]["flight_analysis"]["provenance"]["engine_version"] != "0.0.1"

    # The fleet was rebuilt (not left referencing a stale cache) as part
    # of the same scan — this only proves rebuild_fleet ran without
    # erroring and the flight is still represented; the two engine runs
    # are otherwise identical here, so fleet_key itself isn't expected to
    # change (analysis_key is keyed off the real running engine version,
    # not the provenance string this test corrupted to simulate staleness).
    fleet_after = rpc(registry_server, "get_fleet", {})["result"]
    assert fleet_after["flight_ids"] == [flight_id]


def test_remove_flight_from_watched_folder_reappears_after_rescan(registry_server, tmp_path):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    import shutil
    from ..conftest import LOGS_DIR
    src = LOGS_DIR / "log_20260408_101333_KTOA.csv"
    if not src.exists():
        pytest.skip("real flight logs not available in this environment")
    folder = tmp_path / "logs"
    folder.mkdir()
    shutil.copy(src, folder / src.name)
    rpc(registry_server, "add_log_folder", {"path": str(folder)})
    scanned = rpc(registry_server, "scan_workspace", {})
    [flight_id] = scanned["result"]["new_flight_ids"]

    removed = rpc(registry_server, "remove_flight", {"flight_id": flight_id})
    assert removed["ok"], removed
    assert removed["result"]["removed"] is True
    # still sitting in the reachable folder — the rescan remove_flight
    # triggers finds it again under the same fingerprint
    assert flight_id in removed["result"]["scan_result"]["new_flight_ids"]
    status_list = rpc(registry_server, "list_flights_with_status", {})
    assert any(r["flight_id"] == flight_id for r in status_list["result"]["rows"])


def test_remove_flight_uploaded_only_stays_gone(registry_server):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    flight_header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Temp (deg F)\n"
    high_rpm_rows = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{4000+i},95,180\n" for i in range(240))
    flight_log = (_META + flight_header + high_rpm_rows).encode("utf-8")
    b64 = base64.b64encode(flight_log).decode()

    imported = rpc(registry_server, "import_files", {"files": [{"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"}]})
    assert imported["ok"], imported
    flight_id = imported["result"]["results"][0]["flight_id"]

    removed = rpc(registry_server, "remove_flight", {"flight_id": flight_id})
    assert removed["ok"], removed
    assert removed["result"]["removed"] is True
    assert removed["result"]["scan_result"]["new_flight_ids"] == []
    status_list = rpc(registry_server, "list_flights_with_status", {})
    assert all(r["flight_id"] != flight_id for r in status_list["result"]["rows"])


def test_remove_flights_bulk(registry_server):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    def _upload(n: int) -> str:
        header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Temp (deg F)\n"
        # Distinct dates (not just RPM values) so the two logs fingerprint
        # to different flight_ids rather than colliding as "duplicate".
        rows = "".join(f"2026-01-0{n},12:{i//60:02d}:{i%60:02d},{4000+i},95,180\n" for i in range(240))
        log = (_META + header + rows).encode("utf-8")
        b64 = base64.b64encode(log).decode()
        imp = rpc(registry_server, "import_files", {"files": [{"content_base64": b64, "filename": f"log_2026010{n}_120000_TEST.csv"}]})
        assert imp["ok"], imp
        assert imp["result"]["results"][0]["classification"] == "new", imp
        return imp["result"]["results"][0]["flight_id"]

    id_a = _upload(1)
    id_b = _upload(2)

    removed = rpc(registry_server, "remove_flights", {"flight_ids": [id_a, id_b]})
    assert removed["ok"], removed
    assert set(removed["result"]["removed_flight_ids"]) == {id_a, id_b}
    assert removed["result"]["scan_result"]["new_flight_ids"] == []

    status_list = rpc(registry_server, "list_flights_with_status", {})
    remaining_ids = {r["flight_id"] for r in status_list["result"]["rows"]}
    assert id_a not in remaining_ids
    assert id_b not in remaining_ids


def test_get_save_reset_workspace_rules(registry_server):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    got = rpc(registry_server, "get_workspace_rules", {})
    assert got["ok"], got
    # no active.json written yet — resolved rules equal shipped exactly
    assert got["result"]["rules"] == got["result"]["shipped_rules"]

    shipped = got["result"]["shipped_rules"]
    edited = json.loads(json.dumps(shipped))
    edited["rules"]["overboost_time"]["triggers"][0]["limit"] = 200

    saved = rpc(registry_server, "save_workspace_rules", {"rules": edited})
    assert saved["ok"], saved
    assert saved["result"]["rules"]["rules"]["overboost_time"]["triggers"][0]["limit"] == 200

    refetched = rpc(registry_server, "get_workspace_rules", {})
    assert refetched["result"]["rules"]["rules"]["overboost_time"]["triggers"][0]["limit"] == 200
    # shipped_rules is untouched by the edit — always "what's shipped"
    assert refetched["result"]["shipped_rules"]["rules"]["overboost_time"]["triggers"][0]["limit"] == 300

    reset = rpc(registry_server, "reset_workspace_rules", {})
    assert reset["ok"], reset
    assert reset["result"]["rules"]["rules"]["overboost_time"]["triggers"][0]["limit"] == 300


def test_workspace_rule_edit_changes_live_get_flight_and_list_flights(registry_server):
    """The _resolve_rules wiring: an applied rule edit actually changes
    what get_flight/list_flights_with_status report, not just what
    get_workspace_rules echoes back."""
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Temp (deg F)\n"
    rows = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{4000+i},95,180\n" for i in range(240))
    log = (_META + header + rows).encode("utf-8")
    b64 = base64.b64encode(log).decode()
    imported = rpc(registry_server, "import_files", {"files": [{"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"}]})
    flight_id = imported["result"]["results"][0]["flight_id"]

    # A second flight so the target's leave-one-out baseline isn't empty
    # — oil_temp_peak's threshold check is gated behind having a personal
    # baseline at all (topics.py), same as its baseline_deviation check.
    _import_oil_temp_flight(registry_server, 2, 150)

    before = rpc(registry_server, "get_flight", {"flight_id": flight_id})
    oil_insights_before = [
        i for t in before["result"]["insight_set"]["topics"] if t["topic_id"] == "oil_temp_peak" for i in t["insights"]
    ]
    assert oil_insights_before == []  # 180F is well under the 248F OM limit

    shipped = rpc(registry_server, "get_default_rules", {})["result"]
    edited = json.loads(json.dumps(shipped))
    for trig in edited["rules"]["oil_temp_peak"]["triggers"]:
        if trig["type"] == "threshold":
            trig["limit"] = 100  # far below the synthetic flight's 180F peak
    rpc(registry_server, "save_workspace_rules", {"rules": edited})

    after = rpc(registry_server, "get_flight", {"flight_id": flight_id})
    oil_insights_after = [
        i for t in after["result"]["insight_set"]["topics"] if t["topic_id"] == "oil_temp_peak" for i in t["insights"]
    ]
    assert len(oil_insights_after) == 1
    assert oil_insights_after[0]["trigger"] == "threshold"

    status_list = rpc(registry_server, "list_flights_with_status", {})
    row = next(r for r in status_list["result"]["rows"] if r["flight_id"] == flight_id)
    assert row["worst_severity"] == "limit"


def _import_oil_temp_flight(base_url, day: int, oil_temp_f: int) -> str:
    """day: 1-28, gives each flight a distinct fingerprint-relevant date."""
    date = f"2026-01-{day:02d}"
    header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Temp (deg F)\n"
    rows = "".join(f"{date},12:{i//60:02d}:{i%60:02d},{4000+i},95,{oil_temp_f}\n" for i in range(240))
    log = (_META + header + rows).encode("utf-8")
    b64 = base64.b64encode(log).decode()
    imp = rpc(base_url, "import_files", {"files": [{"content_base64": b64, "filename": f"log_202601{day:02d}_120000_TEST.csv"}]})
    assert imp["ok"], imp
    assert imp["result"]["results"][0]["classification"] == "new", imp
    return imp["result"]["results"][0]["flight_id"]


def test_save_baseline_config_rebuilds_fleet_outliers(registry_server):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    # Five near-identical flights (180F) + one clear outlier (230F).
    for i, temp in enumerate([180, 181, 179, 180, 230]):
        _import_oil_temp_flight(registry_server, i + 1, temp)

    default_fleet = rpc(registry_server, "get_fleet", {})["result"]
    default_outliers = default_fleet["metrics"]["oil_temp_peak"]["outliers"]

    saved = rpc(registry_server, "save_baseline_config", {
        "baseline_config": {"membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 0.5},
    })
    assert saved["ok"], saved
    assert saved["result"]["provenance"]["baseline_config"]["outlier_z_threshold"] == 0.5
    tight_outliers = saved["result"]["metrics"]["oil_temp_peak"]["outliers"]

    # A much looser (smaller |z| required) threshold flags at least as
    # many flights as the shipped 2.0 default did — never fewer.
    assert len(tight_outliers) >= len(default_outliers)

    # Persisted — a fresh get_fleet reflects the saved config, not just
    # the RPC's own response.
    refetched = rpc(registry_server, "get_fleet", {})["result"]
    assert refetched["provenance"]["baseline_config"]["outlier_z_threshold"] == 0.5


def test_what_if_rules_does_not_persist(registry_server):
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})
    # n_min for baseline_deviation defaults to 10 — need leave-one-out n
    # >= 10 (so >= 11 flights total) or the trigger is gated out
    # regardless of threshold, before it ever gets a chance to fire.
    temps = [178, 179, 180, 181, 182, 179, 180, 181, 180, 179, 181, 230]
    for i, temp in enumerate(temps):
        _import_oil_temp_flight(registry_server, i + 1, temp)

    before_fleet = rpc(registry_server, "get_fleet", {})["result"]

    what_if = rpc(registry_server, "what_if_rules", {
        "baseline_config": {"membership": "leave_one_out", "band_kind_by_metric": {}, "outlier_z_threshold": 0.01},
    })
    assert what_if["ok"], what_if
    flights = what_if["result"]["flights"]
    assert len(flights) == len(temps)
    # At |z| >= 0.01 essentially everything deviates from its own
    # leave-one-out mean — "after" should show more baseline_deviation
    # triggers than "before" for at least one flight.
    changed = False
    for entry in flights.values():
        before_bd = sum(
            1 for t in entry["before"]["topics"] if t["topic_id"] == "oil_temp_peak"
            for i in t["insights"] if i["trigger"] == "baseline_deviation"
        )
        after_bd = sum(
            1 for t in entry["after"]["topics"] if t["topic_id"] == "oil_temp_peak"
            for i in t["insights"] if i["trigger"] == "baseline_deviation"
        )
        if after_bd > before_bd:
            changed = True
    assert changed, "expected at least one flight's baseline_deviation trigger to change at |z|>=0.01"

    # Nothing persisted — a fresh fetch matches pre-what_if state exactly.
    after_fleet = rpc(registry_server, "get_fleet", {})["result"]
    assert after_fleet["provenance"]["baseline_config"] == before_fleet["provenance"]["baseline_config"]


def test_analyze_ecu_workspace_reflects_imported_flights(registry_server):
    """Live ECU view data (Spec 03 §5.4): workspace-scoped, computed
    server-side from whatever's already imported — no round trip of full
    FlightAnalysis objects from the client the way op_analyze_ecu needs."""
    rpc(registry_server, "create_workspace", {"name": "N117ZS", "engine_model": "916iS"})

    empty = rpc(registry_server, "analyze_ecu_workspace", {})
    assert empty["ok"], empty
    assert empty["result"]["flight_ids"] == []
    assert empty["result"]["runs"] == []

    header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Press (PSI),CAS Alert\n"
    rows = "".join(
        f"2026-01-01,12:{i//60:02d}:{i%60:02d},4000,90,2.0,{'ENGINE ECU / OIL PRESS' if 5 <= i < 25 else ''}\n"
        for i in range(240)
    )
    log = (_META + header + rows).encode("utf-8")
    b64 = base64.b64encode(log).decode()
    imp = rpc(registry_server, "import_files", {"files": [{"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"}]})
    assert imp["ok"], imp
    flight_id = imp["result"]["results"][0]["flight_id"]

    live = rpc(registry_server, "analyze_ecu_workspace", {})
    assert live["ok"], live
    assert live["result"]["flight_ids"] == [flight_id]
    assert len(live["result"]["runs"]) == 1
    run = live["result"]["runs"][0]
    assert run["flight_id"] == flight_id
    assert run["classification"] == "IN_FLIGHT"
    assert run["co_alerts"] == ["OIL PRESS"]
    assert run["context"]["mean_oil_press_psi"] == 2.0
    assert run["context"]["mean_rpm"] == 4000.0


def test_import_files_writes_flight_sources_for_status_list(server):
    flight_header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Temp (deg F)\n"
    high_rpm_rows = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{4000+i},95,180\n" for i in range(240))
    flight_log = (_META + flight_header + high_rpm_rows).encode("utf-8")
    b64 = base64.b64encode(flight_log).decode()

    imp = rpc(server, "import_files", {"files": [{"content_base64": b64, "filename": "log_20260101_120000_TEST.csv"}]})
    assert imp["ok"], imp
    flight_id = imp["result"]["results"][0]["flight_id"]

    status_list = rpc(server, "list_flights_with_status", {})
    assert status_list["ok"], status_list
    row = next(r for r in status_list["result"]["rows"] if r["flight_id"] == flight_id)
    assert row["status"] == "analyzed"
    assert row["filename"] == "log_20260101_120000_TEST.csv"
    assert row["log_folder"] == "(uploaded)"


def test_get_series_shares_x_grid_across_channels(server):
    # A synced-cursor readout (Spec 05 v0.2) needs every active channel to
    # have a point at the same elapsed_s — independently-downsampled
    # channels used to land at different x values, so ECharts' axis-trigger
    # tooltip only found whichever series happened to be near the cursor.
    high_rpm_rows = "".join(f"2026-01-01,12:{i//60:02d}:{i%60:02d},{4000+i},95,180\n" for i in range(600))
    flight_header = "Date (yyyy-mm-dd),Time (hh:mm:ss),RPM,Indicated Airspeed (kt),Oil Temp (deg F)\n"
    flight_log = (_META + flight_header + high_rpm_rows).encode("utf-8")
    b64 = base64.b64encode(flight_log).decode()

    d = rpc(server, "get_series", {"content_base64": b64, "filename": "x.csv", "channels": ["rpm", "ias_kt", "oil_temp_f"]})
    assert d["ok"], d
    xs = {ch: [p[0] for p in pts] for ch, pts in d["result"].items()}
    assert xs["rpm"] == xs["ias_kt"] == xs["oil_temp_f"]
    assert len(xs["rpm"]) > 0
