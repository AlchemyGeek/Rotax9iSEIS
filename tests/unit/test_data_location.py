"""
Spec 02 v0.10 §5.8.1 — choosing the data location: resolution order,
what choosing a folder would do, moving / using existing, and the
server's missing-location state (Spec 14 v0.12 §5.2, acceptance 19).
"""
import json
import threading

import pytest

from slingology_eis import data_location as dl
from slingology_eis import workspace as ws
from slingology_eis.cli import main
from slingology_eis.host import RpcError, op_change_data_location
from slingology_eis.server import build_server

from .test_server import rpc


@pytest.fixture
def home(tmp_path, monkeypatch):
    """The default data root: an isolated, existing ~/SlingologyEIS with
    one workspace, app settings, and things that aren't part of the root."""
    h = tmp_path / "SlingologyEIS"
    h.mkdir()
    monkeypatch.setattr(dl, "_PACKAGED_HOME", h)
    m = ws.create_workspace(h / "registry.json", h / "workspaces", "N117ZS", "916iS")
    ws.save_app_settings(h / "registry.json", ws.AppSettings(units="metric", last_active_workspace_id=m.id))
    (h / "logs").mkdir()
    (h / "logs" / "flight.csv").write_text("not ours to move")
    return h


def _choose(path):
    dl.location_file().parent.mkdir(parents=True, exist_ok=True)
    dl.location_file().write_text(json.dumps({"version": 1, "data_root": str(path)}))


# ── Resolution order ─────────────────────────────────────────────────────────

def test_resolution_order(home, tmp_path, monkeypatch):
    assert dl.resolve().to_dict() == {"path": str(home), "source": "default", "missing": False}

    chosen = tmp_path / "chosen"
    chosen.mkdir()
    _choose(chosen)
    assert (dl.resolve().root, dl.resolve().source) == (chosen, "chosen")
    assert ws.resolve_registry_path() == chosen / "registry.json"

    monkeypatch.setenv(dl.ENV_VAR, str(tmp_path / "env"))
    assert (dl.resolve().root, dl.resolve().source) == (tmp_path / "env", "environment")


def test_missing_chosen_location_is_never_replaced_by_the_defaults(home, tmp_path):
    _choose(tmp_path / "unplugged")
    r = dl.resolve()
    assert r.missing and r.root == tmp_path / "unplugged"
    with pytest.raises(dl.DataLocationMissing):
        ws.resolve_registry_path()


# ── What choosing a folder would do ──────────────────────────────────────────

def test_assess(home, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / ".DS_Store").write_text("")
    a = dl.assess(empty)
    assert a["action"] == "move" and a["workspace_count"] == 1 and a["bytes"] > 0
    assert dl.assess(tmp_path / "new" / "folder")["action"] == "move"

    existing = tmp_path / "existing"
    ws.create_workspace(existing / "registry.json", existing / "workspaces", "Other", "916iS")
    assert dl.assess(existing) | {} == {"action": "use_existing", "path": str(existing), "workspace_count": 1,
                                        "bytes": None, "reason": None, "code": None}

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "taxes.pdf").write_text("x")
    for target, code in ((unrelated, "NOT_EMPTY"), (home, "SAME_LOCATION"), (home / "sub", "INSIDE_CURRENT"),
                         (tmp_path, "CONTAINS_CURRENT"), (unrelated / "taxes.pdf", "NOT_A_FOLDER")):
        a = dl.assess(target)
        assert (a["action"], a["code"]) == ("refused", code), target
    empty_parent = tmp_path / "parent"
    (empty_parent / "SlingologyEIS").mkdir(parents=True)
    assert dl.assess(empty_parent)["code"] == "NOT_EMPTY"
    assert dl.assess(dl.Path("relative/path"))["code"] == "BAD_PATH"


def test_contains_current_is_refused(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    root = outer / "SlingologyEIS"
    root.mkdir(parents=True)
    monkeypatch.setattr(dl, "_PACKAGED_HOME", root)
    assert dl.assess(outer)["code"] == "CONTAINS_CURRENT"


def test_environment_fixes_the_location(home, tmp_path, monkeypatch):
    monkeypatch.setenv(dl.ENV_VAR, str(home))
    assert dl.assess(tmp_path / "elsewhere")["code"] == "LOCATION_FIXED"
    with pytest.raises(dl.DataLocationError):
        dl.change(tmp_path / "elsewhere")


# ── Moving and using existing ────────────────────────────────────────────────

def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and p.relative_to(root).parts[0] in dl.ROOT_ITEMS}


def test_move_copies_the_root_checks_it_and_keeps_the_old_copy(home, tmp_path):
    before = _snapshot(home)
    target = tmp_path / "drive" / "EIS"
    result = dl.change(target)
    assert result == {"action": "move", "path": str(target), "previous_path": str(home)}
    assert _snapshot(target) == before                       # registry, settings, workspaces
    assert not (target / "logs").exists()                    # not part of the root
    assert _snapshot(home) == before and (home / "logs" / "flight.csv").exists()   # old copy untouched
    assert (dl.resolve().root, dl.resolve().source) == (target, "chosen")
    assert ws.load_app_settings(target / "registry.json").units == "metric"

    # Back to the default: it still holds a registry, so it's used as is,
    # and the location file goes.
    assert dl.assess(dl.default_root())["action"] == "use_existing"
    assert dl.change(dl.default_root())["action"] == "use_existing"
    assert not dl.location_file().exists() and dl.resolve().source == "default"


def test_failed_move_changes_nothing(home, tmp_path, monkeypatch):
    calls = {"n": 0}
    real_copy = dl.shutil.copy2

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_copy(src, dst)

    monkeypatch.setattr(dl.shutil, "copy2", flaky)
    target = tmp_path / "new"
    with pytest.raises(dl.DataLocationError) as e:
        dl.change(target)
    assert e.value.code == "COPY_FAILED" and "disk full" in e.value.message
    assert not target.exists() and not dl.location_file().exists()
    assert dl.resolve().root == home

    pre_existing_empty = tmp_path / "empty"
    pre_existing_empty.mkdir()
    calls["n"] = 0
    with pytest.raises(dl.DataLocationError):
        dl.change(pre_existing_empty)
    assert pre_existing_empty.is_dir() and not any(pre_existing_empty.iterdir())


def test_missing_location_can_start_fresh_or_use_existing(home, tmp_path):
    _choose(tmp_path / "unplugged")
    fresh = tmp_path / "fresh"
    assert dl.assess(fresh)["action"] == "start_fresh"
    assert dl.change(fresh)["action"] == "start_fresh"
    assert dl.resolve().root == fresh and not dl.resolve().missing


# ── Server ───────────────────────────────────────────────────────────────────

def _serve():
    httpd = build_server(logs_dir=None, workspace_dir=None, port=0, quiet=True)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, t, f"http://127.0.0.1:{httpd.server_port}"


def _stop(httpd, t):
    httpd.shutdown()
    httpd.server_close()
    t.join(timeout=5)


def test_server_move_reopens_on_the_same_workspace(home, tmp_path):
    httpd, t, url = _serve()
    try:
        before = rpc(url, "get_active_workspace", {})["result"]
        loc = rpc(url, "get_data_location", {})["result"]
        assert (loc["path"], loc["source"], loc["workspace_count"]) == (str(home), "default", 1)

        target = tmp_path / "moved"
        plan = rpc(url, "assess_data_location", {"path": str(target)})["result"]
        assert plan["action"] == "move"
        res = rpc(url, "change_data_location", {"path": str(target)})["result"]
        assert res["previous_path"] == str(home) and res["location"]["source"] == "chosen"

        after = rpc(url, "get_active_workspace", {})["result"]
        assert after["manifest"]["id"] == before["manifest"]["id"]
        assert rpc(url, "get_app_settings", {})["result"]["units"] == "metric"
        # Writes now land in the new root.
        rpc(url, "create_workspace", {"name": "Second", "engine_model": "916iS"})
        assert ws.list_workspaces(target / "registry.json")[-1].name == "Second"
        assert len(ws.list_workspaces(home / "registry.json")) == 1

        refused = rpc(url, "change_data_location", {"path": str(target / "inside")})
        assert refused["ok"] is False and refused["error"]["code"] == "INSIDE_CURRENT"

        back = rpc(url, "change_data_location", {"default": True})["result"]
        assert back["action"] == "use_existing" and back["location"]["source"] == "default"
    finally:
        _stop(httpd, t)


def test_server_missing_location_blocks_everything_else_until_reachable(home, tmp_path):
    unplugged = tmp_path / "unplugged"
    _choose(unplugged)
    httpd, t, url = _serve()
    try:
        loc = rpc(url, "get_data_location", {})["result"]
        assert loc["missing"] is True and loc["path"] == str(unplugged)
        blocked = rpc(url, "list_workspaces", {})
        assert blocked["error"]["code"] == "DATA_LOCATION_MISSING"
        assert not unplugged.exists()                         # nothing written

        assert rpc(url, "retry_data_location", {})["result"]["missing"] is True
        dl.change(home)                                        # reconnect elsewhere: use the default's data
        assert rpc(url, "retry_data_location", {})["result"]["missing"] is False
        assert len(rpc(url, "list_workspaces", {})["result"]) == 1
    finally:
        _stop(httpd, t)


def test_change_is_refused_during_a_sync(home):
    with pytest.raises(RpcError) as e:
        op_change_data_location({"path": "/tmp/x"}, {"running": {"scan"}})   # the host's own busy state
    assert e.value.code == "BUSY"


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_show_and_set(home, tmp_path, capsys):
    assert main(["data-location"]) == 0
    assert capsys.readouterr().out.strip() == f"{home}  (default location)"

    target = tmp_path / "cli-target"
    assert main(["data-location", "set", str(target), "--quiet"]) == 0
    assert "previous copy is still in" in capsys.readouterr().out
    assert main(["data-location", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["source"] == "chosen"

    assert main(["data-location", "set", str(target / "sub"), "--quiet"]) == 1
    assert main(["data-location", "set"]) == 2


def test_cli_missing_location_is_a_usage_error(home, tmp_path, capsys):
    _choose(tmp_path / "unplugged")
    assert main(["workspace", "list"]) == 2
    assert "can't be reached" in capsys.readouterr().err
