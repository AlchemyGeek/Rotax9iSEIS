"""
Spec 16 D10 / §4.4: the aircraft record in the registry — the migration
from Session D's per-workspace document, export/import of its fields, and
the MCP server opening the aircraft's workspace without asking.
"""
import json

import pytest

from slingology_eis import aircraft as AC
from slingology_eis import workspace as ws
from slingology_eis import workspace_export as wx
from slingology_eis.investigations import mcp_server


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("SLINGOLOGY_EIS_HOME", str(tmp_path))
    return tmp_path


def _legacy_registry(root, names_engines):
    """A registry as Session D left it: workspaces, no aircraft."""
    reg = ws.WorkspaceRegistry()
    for i, (name, engine, opened) in enumerate(names_engines):
        wid = f"ws_{i:012d}"
        reg.workspaces.append(ws.WorkspaceRegistryEntry(id=wid, name=name, engine_model=engine,
                                                        created_at=opened, last_opened_at=opened))
        d = root / "workspaces" / wid
        (d / "flights").mkdir(parents=True)
        ws.save_manifest(d, ws.WorkspaceManifest(id=wid, name=name, engine_model=engine, log_folders=[],
                                                 created_at=opened, updated_at=opened, engine_version_seen=[],
                                                 flight_count=0))
    ws.save_registry(root / "registry.json", reg)
    return [e.id for e in reg.workspaces]


def test_migration_one_aircraft_holding_all(root):
    ids = _legacy_registry(root, [("Old", "916iS", "2026-10-01T00:00:00+00:00"),
                                  ("Main", "916iS", "2026-11-01T00:00:00+00:00"),
                                  ("Other engine", "915iS", "2026-09-01T00:00:00+00:00")])
    (root / "workspaces" / ids[0] / "aircraft.json").write_text(json.dumps(
        {"propeller": "Old prop", "airframe": "Sling", "notes": "old note"}))
    (root / "workspaces" / ids[1] / "aircraft.json").write_text(json.dumps(
        {"propeller": "Airmaster AP332", "notes": "governor note"}))
    assert AC.ensure(root) is True
    every = AC.list_aircraft(root)
    assert len(every) == 1
    a = every[0]
    assert a["name"] == "Rotax 916 iS" and a["engine_model"] == "916iS"
    assert sorted(a["workspaces"]) == sorted(ids)
    assert a["propeller"] == "Airmaster AP332" and a["airframe"] == "Sling"   # most recent wins per field
    notes = AC.read_notes(root, a["id"])
    assert "governor note" in notes and "old note" in notes
    assert not any((root / "workspaces" / i / "aircraft.json").exists() for i in ids)
    reg = ws.load_registry(root / "registry.json")
    assert {e.aircraft_id for e in reg.workspaces} == {a["id"]}
    # Idempotent.
    before = (root / "aircraft" / a["id"] / "aircraft.json").read_text()
    assert AC.ensure(root) is False
    assert (root / "aircraft" / a["id"] / "aircraft.json").read_text() == before


def test_new_workspace_joins_and_delete_leaves(root):
    reg, wroot = root / "registry.json", root / "workspaces"
    m1 = ws.create_workspace(reg, wroot, "One", "916iS")
    m2 = ws.create_workspace(reg, wroot, "Two", "916iS")
    (a,) = AC.list_aircraft(root)
    assert a["workspaces"] == [m1.id, m2.id]
    ws.delete_workspace(reg, wroot, m1.id)
    assert AC.list_aircraft(root)[0]["workspaces"] == [m2.id]


def test_export_carries_fields_not_dirs_or_notes(root, tmp_path_factory):
    reg, wroot = root / "registry.json", root / "workspaces"
    m = ws.create_workspace(reg, wroot, "Mine", "916iS")
    (a,) = AC.list_aircraft(root)
    AC.update(root, a["id"], {"engine_serial": "1234", "propeller": "AP332", "name": "Sling TSi",
                              "documents_dirs": [str(tmp_path_factory.mktemp("docs"))]})
    AC.write_notes(root, a["id"], "private notes")
    out = tmp_path_factory.mktemp("out")
    res = wx.export_workspace(wroot / m.id, out, include_logs=False)
    contents = wx.read_export(res.path)
    carried = contents.documents["aircraft.json"]
    assert carried["engine_serial"] == "1234" and carried["name"] == "Sling TSi"
    assert "documents_dirs" not in carried and "notes" not in carried
    assert "private notes" not in json.dumps(contents.documents)
    # Importing my own export: same engine serial → the same aircraft.
    imp = wx.import_workspace(reg, wroot, contents)
    assert AC.of_workspace(root, imp.id)["id"] == a["id"]
    # A friend's (another serial) → a new aircraft carrying their fields.
    contents.documents["aircraft.json"] = {**carried, "engine_serial": "9999", "name": "Friend's"}
    imp2 = wx.import_workspace(reg, wroot, contents, name="Friend")
    other = AC.of_workspace(root, imp2.id)
    assert other["id"] != a["id"] and other["name"] == "Friend's" and other["documents_dirs"] == []
    # Anonymised: no serial, no chosen name.
    anon = wx.read_export(wx.export_workspace(wroot / m.id, tmp_path_factory.mktemp("anon"),
                                              include_logs=True, anonymise=True).path)
    assert anon.documents["aircraft.json"]["engine_serial"] == "" \
        and anon.documents["aircraft.json"]["name"] == "Rotax 916 iS"


def test_mcp_opens_the_aircraft_workspace(root):
    reg, wroot = root / "registry.json", root / "workspaces"
    mine = ws.create_workspace(reg, wroot, "N1", "916iS")
    scratch = ws.create_workspace(reg, wroot, "Scratch", "916iS")
    friend = AC.create(root, "Friend's", "912iS")
    other = ws.create_workspace(reg, wroot, "Friend ws", "912iS", aircraft_id=friend["id"])
    # The pages last opened the friend's workspace; the server still opens
    # the configured aircraft's most recently opened one.
    app = ws.load_app_settings(reg)
    app.last_active_workspace_id = other.id
    ws.save_app_settings(reg, app)
    r = ws.load_registry(reg)
    for e in r.workspaces:
        e.last_opened_at = {mine.id: "2026-11-02", scratch.id: "2026-11-01", other.id: "2026-11-03"}[e.id]
    ws.save_registry(reg, r)
    (ac,) = [a for a in AC.list_aircraft(root) if mine.id in a["workspaces"]]
    s = mcp_server.Server(aircraft_arg=ac["name"])
    out = s.call_tool("workspaces_list", {})
    res = out["structuredContent"]["result"]
    assert out["structuredContent"]["workspace_id"] == mine.id and res["in_use"] == mine.id
    assert [w["name"] for w in res["workspaces"]] == ["N1", "Scratch"]
    assert res["other_aircraft"][0]["name"] == "Friend's"
    use = s.call_tool("workspace_use", {"workspace_id": "Scratch"})
    assert use["structuredContent"]["workspace_id"] == scratch.id
    assert s.call_tool("flights_list", {})["structuredContent"]["workspace_id"] == scratch.id
    # The registry's last-opened is untouched by workspace_use.
    assert ws.load_app_settings(reg).last_active_workspace_id == other.id
    bad = mcp_server.Server(aircraft_arg="nope").call_tool("flights_list", {})
    assert bad["isError"] and "no aircraft 'nope'" in bad["content"][0]["text"]
    # No --aircraft and several aircraft: the most recently opened workspace's aircraft.
    assert mcp_server.Server().call_tool("workspaces_list", {})["structuredContent"]["workspace_id"] == other.id
